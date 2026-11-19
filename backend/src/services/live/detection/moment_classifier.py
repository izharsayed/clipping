"""Semantic moment classifier using Pydantic AI agent."""

import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from ....config import get_config
from ....ai import _build_transcript_model

logger = logging.getLogger(__name__)


class MomentClassification(BaseModel):
    """Structured AI evaluation of a candidate live stream moment."""

    is_clip_worthy: bool = Field(
        default=True,
        description="True if this is a genuine entertaining, funny, or viral moment worth publishing."
    )
    category: Literal[
        "funny",
        "loud_reaction",
        "exciting_gameplay",
        "conversation",
        "unexpected",
        "emotional",
        "highlight",
    ] = Field(default="highlight", description="Primary category of the event.")
    confidence_score: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0."
    )
    title: str = Field(
        default="", description="Catchy, click-worthy title under 60 characters."
    )
    description: str = Field(
        default="", description="1-2 sentence summary of what happened."
    )
    reason: str = Field(
        default="", description="Why this moment was selected (context, humor, reaction, game clutch)."
    )
    suggested_duration_seconds: int = Field(
        default=35, ge=15, le=60, description="Recommended clip duration in seconds."
    )


class MomentClassifier:
    """Classifies candidate moments using structured LLM evaluation."""

    def __init__(self):
        self._agent: Optional[Agent[None, MomentClassification]] = None

    def _get_agent(self) -> Agent[None, MomentClassification]:
        if self._agent is None:
            config = get_config()
            model = _build_transcript_model(config)
            system_prompt = (
                "You are an elite live stream clipping editor. You analyze streamer moments "
                "combining audio volume/excitement spikes and spoken dialogue transcripts. "
                "Your job is to identify high-retention moments for TikTok, Shorts, and Reels:\n"
                "- Funny reactions, witty remarks, fails, or humor.\n"
                "- Unexpected plot twists, scary events, or shocking statements.\n"
                "- High-energy gaming clutches, aces, or dramatic wins/losses.\n"
                "- Engaging conversational punchlines or storytelling hooks.\n"
                "Reject mundane background noise, coughing, mic bumps, or boring banter even if audio volume was loud. "
                "Be selective: only return is_clip_worthy=True if viewers would watch till the end.\n"
                "Determine suggested_duration_seconds (between 20 and 60 seconds) to capture the complete buildup "
                "and climax without abrupt cutoffs. For quick punchlines use 25-35s; for storytelling, conversational "
                "banter, or game clutch buildup use 40-60s."
            )
            self._agent = Agent(
                model=model,
                output_type=MomentClassification,
                system_prompt=system_prompt,
            )
        return self._agent

    async def classify_moment(
        self,
        transcript: str,
        streamer_name: str,
        game_or_category: Optional[str] = None,
        audio_spike_ratio: float = 1.0,
    ) -> MomentClassification:
        """Evaluate a candidate moment and return structured decision."""
        # If there is literally no spoken words and spike is modest, reject early
        if not transcript.strip() and audio_spike_ratio < 4.0:
            return MomentClassification(
                is_clip_worthy=False,
                category="loud_reaction",
                confidence_score=0.2,
                title="",
                description="Insufficient dialogue or reaction content.",
                reason="Silence or minimal audio activity.",
            )

        agent = self._get_agent()
        prompt = (
            f"Streamer: {streamer_name}\n"
            f"Game/Category: {game_or_category or 'General'}\n"
            f"Audio Excitement Spike: {audio_spike_ratio}x baseline\n"
            f"Dialogue Transcript:\n\"\"\"{transcript}\"\"\"\n\n"
            "Analyze whether this moment is entertaining and worthy of a short-form clip."
        )

        try:
            result = await agent.run(prompt)
            try:
                from ...token_tracker import track_agent_run
                track_agent_run(result, feature="live_moment")
            except Exception:
                pass
            return result.output
        except Exception as exc:
            logger.warning("Moment classification failed: %s; falling back to heuristic", exc)
            # Safe heuristic fallback
            is_worthy = audio_spike_ratio >= 3.0 or len(transcript.split()) >= 15
            return MomentClassification(
                is_clip_worthy=is_worthy,
                category="loud_reaction" if audio_spike_ratio >= 3.0 else "conversation",
                confidence_score=0.7 if is_worthy else 0.3,
                title=f"Crazy Moment from {streamer_name}",
                description=transcript[:100] if transcript else f"Loud reaction on {streamer_name}'s stream",
                reason=f"Detected audio spike ({audio_spike_ratio}x) with spoken dialogue.",
            )
