"""Unit tests for AI Moment Detection and Pipeline Bridge."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.live.detection.audio_energy import AudioEnergyDetector, AudioEnergyResult
from src.services.live.detection.moment_classifier import MomentClassifier, MomentClassification
from src.services.live.detection.orchestrator import LiveMomentOrchestrator
from src.services.live.capture.rolling_buffer import RollingBuffer, SegmentInfo
from src.models import MonitoredChannel, LiveStreamSession, LiveClipMoment


@pytest.mark.asyncio
async def test_audio_energy_detector_spike():
    detector = AudioEnergyDetector(spike_multiplier=2.5, min_rms_threshold=0.01)

    # Simulate quiet baseline segment
    quiet_samples = np.full(16000, 0.02, dtype=np.float32)
    quiet_pcm = quiet_samples.tobytes()

    # Simulate loud reaction spike segment
    loud_samples = np.full(16000, 0.15, dtype=np.float32)
    loud_pcm = loud_samples.tobytes()

    def make_fake_proc(data):
        m = AsyncMock()
        m.returncode = 0
        m.communicate.return_value = (data, b"")
        return m

    # 1. First segment establishes baseline
    with patch("asyncio.create_subprocess_exec", return_value=make_fake_proc(quiet_pcm)):
        res1 = await detector.analyze_segment(Path("seg1.ts"))
        assert res1.rms_energy > 0.01
        assert res1.is_spike is False

    # 2. Quiet second segment maintains baseline
    with patch("asyncio.create_subprocess_exec", return_value=make_fake_proc(quiet_pcm)):
        res2 = await detector.analyze_segment(Path("seg2.ts"))
        assert res2.is_spike is False

    # 3. Loud reaction segment triggers excitement spike!
    with patch("asyncio.create_subprocess_exec", return_value=make_fake_proc(loud_pcm)):
        res3 = await detector.analyze_segment(Path("seg3.ts"))
        assert res3.spike_ratio >= 2.5
        assert res3.is_spike is True


@pytest.mark.asyncio
async def test_moment_classifier_evaluation():
    classifier = MomentClassifier()

    fake_classification = MomentClassification(
        is_clip_worthy=True,
        category="funny",
        confidence_score=0.92,
        title="Unbelievable Missed Shot Reaction",
        description="Streamer laughs uncontrollably after missing an easy shot.",
        reason="High humor and dramatic reaction value.",
        suggested_duration_seconds=25,
    )

    mock_agent = AsyncMock()
    mock_run_result = MagicMock()
    mock_run_result.output = fake_classification
    mock_agent.run.return_value = mock_run_result

    with patch.object(classifier, "_get_agent", return_value=mock_agent):
        res = await classifier.classify_moment(
            transcript="I literally had him in my crosshairs, how did that miss?! No way! Hahaha!",
            streamer_name="shroud",
            game_or_category="VALORANT",
            audio_spike_ratio=3.4,
        )

        assert res.is_clip_worthy is True
        assert res.category == "funny"
        assert res.confidence_score == 0.92
        assert "Missed Shot" in res.title


@pytest.mark.asyncio
async def test_orchestrator_cooldown_and_dispatch(tmp_path: Path):
    buffer = RollingBuffer(buffer_dir=tmp_path)
    orchestrator = LiveMomentOrchestrator(
        channel_id="chan-1",
        session_id="sess-1",
        buffer=buffer,
        cooldown_seconds=45.0,
    )

    # Mock energy detector to return excitement spike
    spike_result = AudioEnergyResult(
        rms_energy=0.15,
        peak_amplitude=0.8,
        baseline_energy=0.03,
        spike_ratio=5.0,
        is_spike=True,
    )

    seg = SegmentInfo(
        index=1,
        file_path=tmp_path / "seg_00001.ts",
        start_time=10.0,
        duration=5.0,
        created_at=100.0,
        size_bytes=1000,
    )

    with patch.object(orchestrator.energy_detector, "analyze_segment", return_value=spike_result):
        with patch.object(orchestrator, "_evaluate_and_clip", new_callable=AsyncMock) as mock_eval:
            # 1. First spike triggers evaluation
            await orchestrator.on_segment_arrived(seg)
            assert mock_eval.called

            # 2. Second spike immediately after within cooldown is ignored
            import time
            orchestrator._last_clip_time = time.time()
            mock_eval.reset_mock()
            await orchestrator.on_segment_arrived(seg)
            assert not mock_eval.called
