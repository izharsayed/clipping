"""Rolling transcriber for candidate live stream windows."""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from ....media.transcription import transcribe_with_whisper
from ....utils.async_helpers import run_in_thread

logger = logging.getLogger(__name__)


class RollingTranscriber:
    """Transcribes audio slices from candidate stream segments."""

    def __init__(self, whisper_model: str = "base"):
        self.whisper_model = whisper_model

    async def transcribe_media(self, media_path: Path) -> Dict[str, Any]:
        """Transcribe a video or audio file using Whisper."""
        try:
            res = await run_in_thread(
                transcribe_with_whisper,
                media_path,
                model_name=self.whisper_model,
            )
            return {
                "text": res.get("text", "").strip(),
                "words": res.get("words", []),
                "segments": res.get("segments", []),
            }
        except Exception as e:
            logger.warning("Transcription failed for candidate window %s: %s", media_path, e)
            return {"text": "", "words": [], "segments": []}
