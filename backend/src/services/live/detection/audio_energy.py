"""Audio energy analysis for live stream segments: detects volume spikes and excitement."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioEnergyResult:
    """Energy analysis result for an individual stream segment."""

    rms_energy: float
    peak_amplitude: float
    baseline_energy: float
    spike_ratio: float
    is_spike: bool


class AudioEnergyDetector:
    """Tracks running baseline energy and flags excitement and loudness spikes."""

    def __init__(
        self,
        spike_multiplier: float = 2.5,
        alpha: float = 0.85,  # Moving average smoothing factor
        min_rms_threshold: float = 0.02,  # Ignore pure silence
    ):
        self.spike_multiplier = spike_multiplier
        self.alpha = alpha
        self.min_rms_threshold = min_rms_threshold
        self.baseline_rms: Optional[float] = None

    async def analyze_segment(self, segment_path: Path) -> AudioEnergyResult:
        """Extract audio samples from video segment and compute RMS & excitement spike."""
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(segment_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "pipe:1",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            raw_pcm, _ = await proc.communicate()

            if proc.returncode != 0 or not raw_pcm:
                return AudioEnergyResult(0.0, 0.0, self.baseline_rms or 0.0, 1.0, False)

            samples = np.frombuffer(raw_pcm, dtype=np.float32)
            if len(samples) == 0:
                return AudioEnergyResult(0.0, 0.0, self.baseline_rms or 0.0, 1.0, False)

            rms = float(np.sqrt(np.mean(samples**2)))
            peak = float(np.max(np.abs(samples)))

            # Update moving average baseline
            if self.baseline_rms is None:
                self.baseline_rms = max(rms, self.min_rms_threshold)
                spike_ratio = 1.0
                is_spike = False
            else:
                effective_baseline = max(self.baseline_rms, self.min_rms_threshold)
                spike_ratio = rms / effective_baseline
                is_spike = spike_ratio >= self.spike_multiplier and rms >= self.min_rms_threshold

                # Only update baseline if not an abnormal spike to avoid shifting baseline upwards
                if not is_spike:
                    self.baseline_rms = (self.alpha * self.baseline_rms) + ((1.0 - self.alpha) * rms)

            return AudioEnergyResult(
                rms_energy=round(rms, 4),
                peak_amplitude=round(peak, 4),
                baseline_energy=round(self.baseline_rms, 4),
                spike_ratio=round(spike_ratio, 2),
                is_spike=is_spike,
            )

        except Exception as exc:
            logger.warning("Failed to analyze audio energy for %s: %s", segment_path, exc)
            return AudioEnergyResult(0.0, 0.0, self.baseline_rms or 0.0, 1.0, False)
