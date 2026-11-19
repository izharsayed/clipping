"""Rolling video buffer: maintains a circular FIFO buffer of live stream segments."""

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_SEGMENT_DURATION_SECONDS = 5.0
DEFAULT_BUFFER_DURATION_SECONDS = 90.0
DEFAULT_MAX_BUFFER_BYTES = 200 * 1024 * 1024  # 200 MB per channel


@dataclass
class SegmentInfo:
    """Metadata for an individual recorded stream segment."""

    index: int
    file_path: Path
    start_time: float  # Monotonic stream elapsed seconds
    duration: float
    created_at: float
    size_bytes: int


class RollingBuffer:
    """Circular FIFO buffer that keeps the most recent N seconds of a stream on disk."""

    def __init__(
        self,
        buffer_dir: Path,
        max_duration_seconds: float = DEFAULT_BUFFER_DURATION_SECONDS,
        max_bytes: int = DEFAULT_MAX_BUFFER_BYTES,
    ):
        self.buffer_dir = Path(buffer_dir)
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.max_duration_seconds = max_duration_seconds
        self.max_bytes = max_bytes
        self.segments: List[SegmentInfo] = []
        self._lock = asyncio.Lock()
        self._elapsed_time: float = 0.0

    async def register_segment(self, file_path: Path, duration: float) -> SegmentInfo:
        """Register a newly completed segment and prune older ones."""
        async with self._lock:
            try:
                size_bytes = file_path.stat().st_size
            except Exception:
                size_bytes = 0

            # Parse index from filename if format is seg_00001.ts
            stem = file_path.stem
            idx = len(self.segments)
            if "_" in stem:
                try:
                    idx = int(stem.split("_")[-1])
                except ValueError:
                    pass

            start_time = self._elapsed_time
            self._elapsed_time += duration

            seg = SegmentInfo(
                index=idx,
                file_path=file_path,
                start_time=start_time,
                duration=duration,
                created_at=time.time(),
                size_bytes=size_bytes,
            )
            self.segments.append(seg)
            await self._prune_expired_locked()
            return seg

    async def _prune_expired_locked(self) -> None:
        """Remove segments that fall outside the rolling window or exceed byte caps."""
        if not self.segments:
            return

        latest_end_time = self.segments[-1].start_time + self.segments[-1].duration
        min_allowed_time = latest_end_time - self.max_duration_seconds

        to_remove = []
        total_bytes = sum(s.size_bytes for s in self.segments)

        for s in self.segments:
            # Segment has completely aged out past the retention window
            seg_end = s.start_time + s.duration
            if seg_end < min_allowed_time or total_bytes > self.max_bytes:
                to_remove.append(s)
                total_bytes -= s.size_bytes
            else:
                break

        for s in to_remove:
            self.segments.remove(s)
            try:
                if s.file_path.exists():
                    s.file_path.unlink(missing_ok=True)
                    logger.debug("Pruned expired buffer segment: %s", s.file_path.name)
            except Exception as e:
                logger.warning("Could not unlink segment %s: %s", s.file_path, e)

    async def extract_window(
        self,
        start_seconds: float,
        end_seconds: float,
        output_path: Path,
        pre_roll_seconds: float = 0.0,
        post_roll_seconds: float = 0.0,
    ) -> Path:
        """
        Extract a continuous video window from the buffered segments.
        Guarantees that boundaries are clamped to available buffer history
        so future non-existent timestamps never cause clip truncation.
        """
        async with self._lock:
            if not self.segments:
                raise RuntimeError("Cannot extract clip: Rolling buffer is empty")

            buffer_start = self.segments[0].start_time
            buffer_end = self.segments[-1].start_time + self.segments[-1].duration
            requested_duration = max(5.0, end_seconds - start_seconds)

            # In a live stream, target_end cannot exceed the latest recorded segment:
            target_end = min(end_seconds + post_roll_seconds, buffer_end)
            # Pull start backwards from target_end so full duration is retained from history:
            target_start = max(buffer_start, target_end - requested_duration - pre_roll_seconds)
            target_duration = max(1.0, target_end - target_start)

            # Find all segments that overlap with [target_start, target_end]
            matching_segments: List[SegmentInfo] = []
            for s in self.segments:
                s_end = s.start_time + s.duration
                if s_end > target_start and s.start_time < target_end:
                    matching_segments.append(s)

            if not matching_segments:
                # Fallback to the latest available segments if timestamps drifted
                matching_segments = self.segments[-max(1, int(target_duration / 5)) :]

            first_segment = matching_segments[0]
            offset_within_first = max(0.0, target_start - first_segment.start_time)

            # Build temporary concat list
            concat_list_file = self.buffer_dir / f"concat_{int(time.time() * 1000)}.txt"
            lines = [f"file '{s.file_path.resolve().as_posix()}'\n" for s in matching_segments]
            concat_list_file.write_text("".join(lines), encoding="utf-8")

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Fast concatenation and precise trimming using FFmpeg concat demuxer
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_file),
                "-ss",
                str(round(offset_within_first, 3)),
                "-t",
                str(round(target_duration, 3)),
                "-c",
                "copy",
                "-bsf:a",
                "aac_adtstoasc",
                "-movflags",
                "+faststart",
                str(output_path),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            # Clean up the concat file
            concat_list_file.unlink(missing_ok=True)

            if proc.returncode != 0 or not output_path.exists():
                logger.error(
                    "FFmpeg buffer slice failed (code %d): %s",
                    proc.returncode,
                    stderr.decode(errors="replace"),
                )
                raise RuntimeError(f"FFmpeg extraction failed: {stderr.decode(errors='replace')[:200]}")

            logger.info("Successfully extracted live buffer window to %s (%d bytes)", output_path, output_path.stat().st_size)
            return output_path

    async def get_buffer_stats(self) -> dict:
        """Return current stats of the rolling buffer."""
        async with self._lock:
            total_duration = sum(s.duration for s in self.segments)
            total_bytes = sum(s.size_bytes for s in self.segments)
            return {
                "segment_count": len(self.segments),
                "total_duration_seconds": round(total_duration, 2),
                "total_bytes": total_bytes,
                "earliest_timestamp": self.segments[0].start_time if self.segments else 0.0,
                "latest_timestamp": (self.segments[-1].start_time + self.segments[-1].duration) if self.segments else 0.0,
            }

    async def clear(self) -> None:
        """Purge all segments and remove buffer folder."""
        async with self._lock:
            self.segments.clear()
            try:
                shutil.rmtree(self.buffer_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Failed to remove buffer directory %s: %s", self.buffer_dir, e)
