"""
Post Text Service: generates and formats PeakCut 'Post Text' metadata for clips.
Includes:
- Hook (up to 5 words, ALL CAPS for on-screen stop-scrolling text)
- Title (CTR-optimized title under 70 characters)
- Description (1-2 concise sentences summarizing the moment)
- Hashtags (5 to 8 targeted tags without #)
- Highlight Words (spoken punch words colorized in captions)
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from ..config import get_config
from ..ai import _build_transcript_model

logger = logging.getLogger(__name__)

POST_TEXT_SYSTEM_PROMPT = """You write social media post metadata (PeakCut Post Text) for short-form clips (YouTube Shorts, TikTok, Instagram Reels).
Rules:
- hook: at most 5 words, ALL CAPS, shown as big on-screen text on the video. Curiosity-driven, but strictly true to what happens in the clip.
- title: at most 70 characters, optimized for click-through rate. No clickbait lies, punchy and engaging.
- description: 1 or 2 concise sentences summarizing the moment and driving engagement.
- hashtags: 5 to 8 targeted tags without the # sign and without punctuation.
- highlight_words: 3 to 6 single punch words spoken in the clip that carry the emotional or dramatic weight.
Never include quotes, markdown formatting, or outside links. Write in the language of the transcript."""


class PostText(BaseModel):
    hook: str = Field(
        default="",
        description="At most 5 words, ALL CAPS, shown as big text on the video. E.g. NEVER STAY IN THIS",
    )
    title: str = Field(
        default="",
        description="At most 70 characters, punchy title for the post.",
    )
    description: str = Field(
        default="",
        description="1 or 2 concise sentences summarizing the moment.",
    )
    hashtags: List[str] = Field(
        default_factory=list,
        description="5 to 8 targeted tags without the # sign and without punctuation.",
    )
    highlight_words: List[str] = Field(
        default_factory=list,
        description="3 to 6 single words spoken in the clip that carry the punch.",
    )


def tidy_post_text(
    data: Dict[str, Any],
    fallback_title: str = "",
    text: str = "",
) -> Dict[str, Any]:
    """Sanitize and format post_text into standard shape with clamped lengths."""
    hook = str(data.get("hook") or "").strip()
    # Ensure hook is uppercase and at most 5-6 words
    words = hook.split()
    if len(words) > 5:
        hook = " ".join(words[:5])
    hook = re.sub(r'["\']', '', hook).upper()

    title = str(data.get("title") or fallback_title or "Viral Clip").strip()
    title = re.sub(r'["\']', '', title)
    if len(title) > 80:
        title = title[:77] + "..."

    description = str(data.get("description") or "").strip()
    if not description and text:
        # Fallback to first sentence of text
        sentences = [s.strip() for s in re.split(r'[.!?]', text) if s.strip()]
        description = (sentences[0] + ".") if sentences else text[:120]

    raw_tags = data.get("hashtags")
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split()
    elif not isinstance(raw_tags, list):
        raw_tags = []

    clean_tags: List[str] = []
    for tag in raw_tags:
        clean = re.sub(r"[^\w]", "", str(tag))
        if clean and len(clean) >= 2 and clean.lower() not in [t.lower() for t in clean_tags]:
            clean_tags.append(clean)
        if len(clean_tags) >= 8:
            break

    if len(clean_tags) < 3:
        clean_tags.extend(["viral", "shorts", "trending", "clip", "mustwatch"][: 5 - len(clean_tags)])

    raw_highlights = data.get("highlight_words")
    if isinstance(raw_highlights, str):
        raw_highlights = raw_highlights.split()
    elif not isinstance(raw_highlights, list):
        raw_highlights = []

    clean_highlights: List[str] = []
    for hw in raw_highlights:
        cleaned = re.sub(r"[^\w]", "", str(hw)).lower()
        if cleaned and len(cleaned) >= 3 and cleaned not in clean_highlights:
            clean_highlights.append(cleaned)
        if len(clean_highlights) >= 6:
            break

    formatted_copy = format_post_text_clipboard(title, description, clean_tags)

    return {
        "hook": hook or "WATCH THIS",
        "title": title,
        "description": description,
        "hashtags": clean_tags,
        "highlight_words": clean_highlights,
        "formatted_copy": formatted_copy,
    }


def format_post_text_clipboard(title: str, description: str, hashtags: List[str]) -> str:
    """Format post text as:
    [Title]

    [Description]

    #tag1 #tag2 #tag3 ...
    """
    tag_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags if t)
    parts = [title.strip()]
    if description.strip():
        parts.append(description.strip())
    if tag_str:
        parts.append(tag_str)
    return "\n\n".join(parts)


async def generate_post_text_with_ai(
    clip_text: str,
    clip_title: Optional[str] = None,
    source_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the configured LLM to generate PeakCut Post Text for a clip."""
    from pydantic_ai import Agent

    runtime_config = get_config()
    model = _build_transcript_model(runtime_config)

    agent = Agent[None, PostText](
        model=model,
        output_type=PostText,
        system_prompt=POST_TEXT_SYSTEM_PROMPT,
        output_retries=2,
    )

    prompt_parts = []
    if source_title:
        prompt_parts.append(f"Full Video Title: {source_title}")
    if clip_title:
        prompt_parts.append(f"Working Clip Title: {clip_title}")
    prompt_parts.append(f"Clip Transcript:\n{clip_text}")

    prompt = "\n\n".join(prompt_parts)

    try:
        result = await asyncio.wait_for(agent.run(prompt), timeout=45)
        try:
            from .token_tracker import track_agent_run
            track_agent_run(result, feature="post_text")
        except Exception:
            pass
        raw = result.output.model_dump()
        return tidy_post_text(raw, fallback_title=clip_title or "", text=clip_text)
    except Exception as exc:
        logger.warning("AI post text generation failed: %s; using smart fallback", exc)
        return generate_fallback_post_text(clip_text, clip_title)


def generate_fallback_post_text(clip_text: str, clip_title: Optional[str] = None) -> Dict[str, Any]:
    """Deterministic fallback post text when LLM is unavailable."""
    title = (clip_title or "Unbelievable Moment")[:70]
    words = [w for w in re.split(r"\s+", clip_text) if w]
    first_few = " ".join(words[:4]).upper() if words else "WATCH THIS"
    hook = re.sub(r"[^\w\s]", "", first_few).strip()

    sentences = [s.strip() for s in re.split(r"[.!?]", clip_text) if len(s.strip()) > 10]
    desc = sentences[0] + "." if sentences else clip_text[:120]

    return tidy_post_text(
        {
            "hook": hook,
            "title": title,
            "description": desc,
            "hashtags": ["viral", "fyp", "trending", "clip", "shorts"],
            "highlight_words": words[:4] if words else [],
        },
        fallback_title=title,
        text=clip_text,
    )
