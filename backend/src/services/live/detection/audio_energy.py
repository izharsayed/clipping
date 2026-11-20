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
        vocal_isolation: bool = True,
    ):
        self.spike_multiplier = spike_multiplier
        self.alpha = alpha
        self.min_rms_threshold = min_rms_threshold
        self.vocal_isolation = vocal_isolation
        self.baseline_rms: Optional[float] = None
        self.threshold_percent: int = 80
        self.current_mode: str = "Balanced Hype"

    def set_sensitivity(self, threshold_percent: int, mode: str = "Balanced Hype") -> None:
        """
        Dynamically tunes spike multiplier based on channel's Virality Threshold (50-95%) and mode.
        - Higher threshold (85-95%) requires a larger vocal spike (strict viral filtering).
        - Lower threshold (50-65%) is more sensitive to conversational energy.
        """
        self.threshold_percent = max(50, min(95, threshold_percent))
        self.current_mode = mode or "Balanced Hype"

        # Linear mapping: 50% -> 1.8x, 80% -> 2.6x, 95% -> 3.5x
        norm = (self.threshold_percent - 50) / 45.0
        base_multiplier = 1.8 + (norm * 1.7)

        if self.current_mode == "Loud Reactions":
            # Strict screaming / shouting filter
            self.spike_multiplier = round(base_multiplier * 1.15, 2)
        elif self.current_mode == "Dialogue & Story":
            # Catches subtle narrative punchlines and conversational spikes
            self.spike_multiplier = round(base_multiplier * 0.85, 2)
        elif self.current_mode == "Gameplay Action":
            self.spike_multiplier = round(base_multiplier * 1.0, 2)
        else:  # "Balanced Hype"
            self.spike_multiplier = round(base_multiplier, 2)

        logger.debug(
            "Tuned AudioEnergyDetector sensitivity: threshold=%d%%, mode='%s' -> spike_multiplier=%.2fx",
            self.threshold_percent,
            self.current_mode,
            self.spike_multiplier,
        )

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
        ]
        if self.vocal_isolation:
            # Vocal bandpass filter (200Hz - 3500Hz) rejects low-end rumble (explosions, engines)
            # and high-frequency hiss, isolating human speech and vocal excitement.
            cmd.extend(["-af", "highpass=f=200,lowpass=f=3500"])
        cmd.extend([
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "pipe:1",
        ])

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
