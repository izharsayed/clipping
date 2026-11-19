"""Unit tests for the Rolling Video Buffer and Live Capture Engine."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.live.capture.rolling_buffer import RollingBuffer, SegmentInfo
from src.services.live.capture.capture_manager import LiveCaptureManager
from src.services.live.capture.stream_capture import LiveStreamCaptureEngine


@pytest.mark.asyncio
async def test_rolling_buffer_register_and_prune(tmp_path: Path):
    buffer = RollingBuffer(
        buffer_dir=tmp_path,
        max_duration_seconds=15.0,  # Keep only 15 seconds
        max_bytes=100 * 1024 * 1024,
    )

    # Create dummy segment files
    seg_files = []
    for i in range(5):
        f = tmp_path / f"seg_{i:05d}.ts"
        f.write_bytes(b"dummy ts data " * 100)
        seg_files.append(f)

    # Register segments of 5.0 seconds each (total 25s > 15s)
    for i, f in enumerate(seg_files):
        await buffer.register_segment(f, duration=5.0)

    # Because max_duration is 15s, earlier segments should have been pruned!
    stats = await buffer.get_buffer_stats()
    assert stats["segment_count"] <= 4
    # The first segment (seg_00000.ts) should have been unlinked
    assert not seg_files[0].exists()
    # The latest segments should still exist
    assert seg_files[-1].exists()


@pytest.mark.asyncio
async def test_rolling_buffer_extract_window(tmp_path: Path):
    buffer = RollingBuffer(buffer_dir=tmp_path, max_duration_seconds=60.0)

    # Create 4 dummy segments
    for i in range(4):
        f = tmp_path / f"seg_{i:05d}.ts"
        f.write_bytes(b"fake ts video")
        await buffer.register_segment(f, duration=5.0)

    output_clip = tmp_path / "output_test_clip.mp4"

    # Mock asyncio subprocess for ffmpeg
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"", b"")

    # Create dummy output file on disk so exists() returns True
    def fake_subprocess(*args, **kwargs):
        output_clip.write_bytes(b"rendered mp4 clip")
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_subprocess):
        res = await buffer.extract_window(
            start_seconds=5.0,
            end_seconds=15.0,
            output_path=output_clip,
            pre_roll_seconds=0.0,
            post_roll_seconds=0.0,
        )
        assert res == output_clip
        assert output_clip.exists()


@pytest.mark.asyncio
async def test_rolling_buffer_dynamic_duration_bounds(tmp_path: Path):
    """Verify that extract_window never projects into the future and preserves requested duration."""
    buffer = RollingBuffer(buffer_dir=tmp_path, max_duration_seconds=90.0)

    # Register 12 segments of 5s each (total 60.0s recorded, timestamps 0.0 to 60.0)
    for i in range(12):
        f = tmp_path / f"seg_{i:05d}.ts"
        f.write_bytes(b"stream_segment_data")
        await buffer.register_segment(f, duration=5.0)

    output_clip = tmp_path / "dynamic_clip.mp4"
    captured_cmd = []

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"", b"")

    def capture_subprocess(*args, **kwargs):
        captured_cmd.extend(args)
        output_clip.write_bytes(b"dynamic_clip_output")
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=capture_subprocess):
        # Request 45.0s ending at current stream time (60.0s)
        await buffer.extract_window(
            start_seconds=15.0,
            end_seconds=60.0,
            output_path=output_clip,
            pre_roll_seconds=0.0,
            post_roll_seconds=0.0,
        )
        assert output_clip.exists()
        # Ensure -t argument in ffmpeg command is 45.0 (not truncated to 20.0!)
        t_index = captured_cmd.index("-t")
        assert captured_cmd[t_index + 1] == "45.0"


@pytest.mark.asyncio
async def test_capture_manager_lifecycle(tmp_path: Path):
    manager = LiveCaptureManager.get_instance()
    manager.base_buffer_dir = tmp_path

    async def fake_start(self_engine):
        self_engine._running = True
        return True

    with patch.object(LiveStreamCaptureEngine, "start", fake_start):
        started = await manager.start_capture(
            channel_id="chan-1",
            session_id="sess-1",
            stream_url="https://twitch.tv/shroud",
        )
        assert started is True
        assert manager.is_capturing("chan-1") is True
        assert manager.get_buffer("chan-1") is not None

        # Stopping capture
        with patch.object(LiveStreamCaptureEngine, "cleanup", return_value=None):
            await manager.stop_capture("chan-1", cleanup_disk=True)
            assert manager.is_capturing("chan-1") is False
            assert manager.get_buffer("chan-1") is None
