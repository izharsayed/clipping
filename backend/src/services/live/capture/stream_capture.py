"""Live stream capture worker: records live streams into a segmented rolling buffer."""

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

from .rolling_buffer import RollingBuffer, SegmentInfo
from ....utils.async_helpers import run_in_thread

logger = logging.getLogger(__name__)


class LiveStreamCaptureEngine:
    """Manages stream recording process into a RollingBuffer with automatic segment rotation."""

    def __init__(
        self,
        channel_id: str,
        session_id: str,
        stream_url: str,
        buffer_dir: Path,
        segment_duration: float = 5.0,
        max_buffer_duration: float = 90.0,
        on_segment_callback: Optional[Callable[[SegmentInfo], None]] = None,
    ):
        self.channel_id = channel_id
        self.session_id = session_id
        self.stream_url = stream_url
        self.buffer_dir = Path(buffer_dir)
        self.segment_duration = segment_duration
        self.max_buffer_duration = max_buffer_duration
        self.on_segment_callback = on_segment_callback

        self.buffer = RollingBuffer(
            buffer_dir=self.buffer_dir,
            max_duration_seconds=max_buffer_duration,
        )
        if self.on_segment_callback is None:
            from ..detection.orchestrator import LiveMomentOrchestrator
            self.orchestrator = LiveMomentOrchestrator(
                channel_id=self.channel_id,
                session_id=self.session_id,
                buffer=self.buffer,
            )
            self.on_segment_callback = self.orchestrator.on_segment_arrived
        else:
            self.orchestrator = None

        self._process: Optional[asyncio.subprocess.Process] = None
        self._running: bool = False
        self._watcher_task: Optional[asyncio.Task] = None
        self._registered_files: set = set()

    async def resolve_playback_url(self) -> Optional[str]:
        """Resolve live HLS playback URL using streamlink with yt-dlp fallback."""
        def resolve_streamlink():
            try:
                import streamlink
                session = streamlink.Streamlink()
                # Set a polite user agent
                session.set_option("http-headers", {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                })
                streams = session.streams(self.stream_url)
                if streams:
                    chosen = streams.get("720p60") or streams.get("720p") or streams.get("best") or streams.get("worst")
                    if chosen:
                        return getattr(chosen, "url", None) or chosen.to_manifest_url()
            except Exception as e:
                logger.warning("Streamlink playback resolve failed for %s: %s", self.stream_url, e)
            return None

        playback_url = await run_in_thread(resolve_streamlink)
        if playback_url:
            return playback_url

        # Fallback to yt-dlp
        def resolve_ytdl():
            try:
                import yt_dlp
                ydl_opts = {
                    "skip_download": True,
                    "quiet": True,
                    "no_warnings": True,
                    "format": "best[ext=mp4]/best",
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.stream_url, download=False)
                    return info.get("url")
            except Exception as e:
                logger.warning("yt-dlp playback resolve failed for %s: %s", self.stream_url, e)
                return None

        return await run_in_thread(resolve_ytdl)

    async def start(self) -> bool:
        """Start capturing the stream into the rolling buffer."""
        if self._running:
            return True

        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        playback_url = await self.resolve_playback_url()
        if not playback_url:
            logger.error("Could not resolve playback URL for %s", self.stream_url)
            return False

        segment_pattern = str(self.buffer_dir / "seg_%05d.ts")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            playback_url,
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(self.segment_duration),
            "-segment_format",
            "mpegts",
            "-reset_timestamps",
            "1",
            segment_pattern,
        ]

        logger.info("Starting stream capture for %s -> %s", self.stream_url, self.buffer_dir)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            self._running = True
            self._watcher_task = asyncio.create_task(self._watch_segments())
            return True
        except Exception as exc:
            logger.exception("Failed to start FFmpeg stream capture: %s", exc)
            self._running = False
            return False

    async def _watch_segments(self) -> None:
        """Continuously monitors buffer_dir for newly generated segments."""
        while self._running:
            try:
                files = sorted(self.buffer_dir.glob("seg_*.ts"))
                # Only register segments once there is at least one newer segment being written
                # to ensure the previous file is completely flushed by FFmpeg.
                if len(files) > 1:
                    for f in files[:-1]:
                        if f not in self._registered_files:
                            self._registered_files.add(f)
                            # Probe duration or estimate from segment_duration
                            seg_info = await self.buffer.register_segment(
                                file_path=f,
                                duration=self.segment_duration,
                            )
                            if self.on_segment_callback:
                                try:
                                    if asyncio.iscoroutinefunction(self.on_segment_callback):
                                        await self.on_segment_callback(seg_info)
                                    else:
                                        self.on_segment_callback(seg_info)
                                except Exception as cb_err:
                                    logger.exception("Error in on_segment_callback: %s", cb_err)

                # Check if ffmpeg died
                if self._process and self._process.returncode is not None:
                    logger.warning(
                        "Stream capture FFmpeg process exited with code %s",
                        self._process.returncode,
                    )
                    break

            except Exception as e:
                logger.warning("Error in segment watcher loop: %s", e)

            await asyncio.sleep(2.0)

        self._running = False

    async def stop(self) -> None:
        """Stop capturing and terminate FFmpeg gracefully."""
        self._running = False
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        logger.info("Stream capture stopped for channel %s", self.channel_id)

    async def cleanup(self) -> None:
        """Stop and remove all buffer data from disk."""
        await self.stop()
        await self.buffer.clear()
