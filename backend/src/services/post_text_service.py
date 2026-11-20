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
- hook: at most 5 words, ALL CAPS, shown as big on-screen text on the video. Curiosity-driven, punchy, engaging, and strictly true to what happens in the clip (e.g. STEALING A JUMBO JET, INSANE 5 STAR CHASE). Never cut off mid-sentence.
- title: at most 70 characters, optimized for click-through rate. No clickbait lies, punchy and engaging.
- description: 1 or 2 concise sentences summarizing the moment and driving engagement.
- hashtags: 5 to 8 targeted tags without the # sign and without punctuation, highly relevant to the specific topic and content of the video.
- youtube_tags: 10 to 15 search keywords / tags for YouTube Studio SEO, highly relevant to the clip, game, and topic (e.g. gta 6, gta vi, gta 6 gameplay, jumbo jet heist, rockstar games).
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
    youtube_tags: List[str] = Field(
        default_factory=list,
        description="10 to 15 targeted search keywords / tags for YouTube Studio.",
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

    raw_yt_tags = data.get("youtube_tags") or data.get("tags")
    if isinstance(raw_yt_tags, str):
        raw_yt_tags = [t.strip() for t in raw_yt_tags.split(",") if t.strip()]
    elif not isinstance(raw_yt_tags, list):
        raw_yt_tags = []

    clean_yt_tags: List[str] = []
    for tag in raw_yt_tags:
        clean = re.sub(r'["\'#]', '', str(tag)).strip()
        if clean and len(clean) >= 2 and clean.lower() not in [t.lower() for t in clean_yt_tags]:
            clean_yt_tags.append(clean)
        if len(clean_yt_tags) >= 15:
            break

    if not clean_yt_tags:
        clean_yt_tags = [title.lower()] + [t.lower() for t in clean_tags]

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

    formatted_copy = format_post_text_clipboard(title, description, clean_tags, clean_yt_tags)

    return {
        "hook": hook or "WATCH THIS",
        "title": title,
        "description": description,
        "hashtags": clean_tags,
        "youtube_tags": clean_yt_tags,
        "highlight_words": clean_highlights,
        "formatted_copy": formatted_copy,
    }


def format_post_text_clipboard(
    title: str,
    description: str,
    hashtags: List[str],
    youtube_tags: Optional[List[str]] = None,
) -> str:
    """Format post text for clipboard copying with tags."""
    tag_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags if t)
    parts = [title.strip()]
    if description.strip():
        parts.append(description.strip())
    if tag_str:
        parts.append(tag_str)
    if youtube_tags:
        parts.append("Tags:\n" + ", ".join(youtube_tags))
    return "\n\n".join(parts)


async def generate_post_text_with_ai(
    clip_text: str,
    clip_title: Optional[str] = None,
    source_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the configured LLM (with graceful model fallbacks) to generate PeakCut Post Text for a clip."""
    from pydantic_ai import Agent

    runtime_config = get_config()
    primary_model = _build_transcript_model(runtime_config)

    candidate_models = [primary_model]
    # If using Google models, prepare high-quota lite fallbacks to prevent 429 rate limit failures
    if "flash" in str(primary_model).lower() or "google" in str(primary_model).lower():
        for fallback in [
            "google-gla:gemini-3.1-flash-lite-preview",
            "google-gla:gemini-3.1-flash-lite",
            "google-gla:gemini-3.5-flash-lite",
        ]:
            if fallback != str(primary_model) and fallback not in candidate_models:
                candidate_models.append(fallback)

    prompt_parts = []
    if source_title:
        prompt_parts.append(f"Full Video Title: {source_title}")
    if clip_title:
        prompt_parts.append(f"Working Clip Title: {clip_title}")
    prompt_parts.append(f"Clip Transcript:\n{clip_text}")

    prompt = "\n\n".join(prompt_parts)

    last_error = None
    for model_candidate in candidate_models:
        try:
            agent = Agent[None, PostText](
                model=model_candidate,
                output_type=PostText,
                system_prompt=POST_TEXT_SYSTEM_PROMPT,
                output_retries=2,
            )
            result = await asyncio.wait_for(agent.run(prompt), timeout=45)
            try:
                from .token_tracker import track_agent_run
                track_agent_run(result, feature="post_text")
            except Exception:
                pass
            raw = result.output.model_dump()
            return tidy_post_text(raw, fallback_title=clip_title or "", text=clip_text)
        except Exception as exc:
            last_error = exc
            logger.warning("Post text generation with %s failed: %s; trying next model", model_candidate, exc)
            continue

    logger.warning("All AI post text models failed (%s); using smart contextual fallback", last_error)
    return generate_fallback_post_text(clip_text, clip_title, source_title)


def generate_fallback_post_text(
    clip_text: str,
    clip_title: Optional[str] = None,
    source_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic, context-rich fallback post text when LLM is unavailable."""
    title = (clip_title or "Unbelievable Moment").strip()[:70]

    # Generate hook from clip_title or strong action words instead of raw transcript prefix
    if clip_title and len(clip_title.split()) >= 2:
        title_words = clip_title.split()
        hook_words = [w for w in title_words[:5] if w.lower() not in {"in", "on", "at", "the", "a", "an"} or len(title_words) <= 3]
        if not hook_words:
            hook_words = title_words[:4]
        hook = " ".join(hook_words).upper()
    else:
        words = [w for w in re.split(r"\s+", clip_text) if w and len(w) > 2]
        hook = "WATCH THIS MOMENT" if not words else f"UNREAL {words[0].upper()}"

    sentences = [s.strip() for s in re.split(r"[.!?]", clip_text) if len(s.strip()) > 10]
    if len(sentences) >= 2:
        desc = f"{sentences[0]}. {sentences[1]}."
    elif sentences:
        desc = f"{sentences[0]}."
    else:
        desc = clip_text[:140]

    combined_ctx = f"{source_title or ''} {clip_title or ''} {clip_text[:300]}".lower()
    candidate_tags = []
    stopwords = {"this", "that", "with", "from", "have", "were", "what", "when", "your", "they", "will", "been", "there", "about", "just", "like", "know"}
    for word in re.findall(r"[a-zA-Z0-9]{3,}", combined_ctx):
        if word not in stopwords and word not in candidate_tags:
            candidate_tags.append(word)
        if len(candidate_tags) >= 8:
            break

    if len(candidate_tags) < 3:
        candidate_tags.extend(["viral", "shorts", "trending", "clip", "mustwatch"][: 5 - len(candidate_tags)])

    words_in_transcript = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", clip_text)]
    highlight_candidates = [w for w in words_in_transcript if w not in stopwords and w not in {"found", "have"}]
    if not highlight_candidates:
        highlight_candidates = words_in_transcript[:4]

    yt_tags = []
    if clip_title:
        yt_tags.append(clip_title.lower())
    if source_title:
        yt_tags.append(source_title.lower())
    for tag in candidate_tags:
        if tag not in yt_tags:
            yt_tags.append(tag)
    yt_tags.extend(["shorts", "viral clip", "trending"])

    return tidy_post_text(
        {
            "hook": hook,
            "title": title,
            "description": desc,
            "hashtags": candidate_tags[:7],
            "youtube_tags": yt_tags[:12],
            "highlight_words": highlight_candidates[:5],
        },
        fallback_title=title,
        text=clip_text,
    )
