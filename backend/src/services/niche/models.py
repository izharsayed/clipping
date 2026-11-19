"""Pydantic schemas and metadata for the 7 YouTube/TikTok gaming niches."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

NicheType = Literal["commentary", "compare", "stunts", "myths", "moments", "rank", "skit"]

NICHE_METADATA = {
    "commentary": {
        "id": "commentary",
        "name": "Commentary Over Gameplay",
        "tagline": "AI voiceover with word captions & pop-up images over moving gameplay",
        "icon": "Mic",
        "badge": "Viral Leader",
        "avg_views": "5M - 200M+",
        "description": "A high-retention vertical Short featuring a punchy voiceover, dynamic animated captions in the center, royalty-free images popping up at key keywords, and continuous moving gameplay underneath (driving, flying, parkour).",
        "difficulty": "Easy",
        "recommended_length": "25 - 50 seconds",
    },
    "compare": {
        "id": "compare",
        "name": "Game Comparisons",
        "tagline": "Stacked 2-game split screen synced at the exact second of impact",
        "icon": "SplitSquareVertical",
        "badge": "High Engagement",
        "avg_views": "10M - 500M+",
        "description": "Two games stacked vertically (e.g. GTA 6 on top vs. GTA 5 on bottom, or physics/water/crash comparisons), synchronized down to the exact frame of the impact, with clean modern pill labels.",
        "difficulty": "Medium",
        "recommended_length": "20 - 45 seconds",
    },
    "stunts": {
        "id": "stunts",
        "name": "Stunts & Trickshots",
        "tagline": "The fails first (Attempt #1..#N), the landing last + 0.5x slow-mo replay",
        "icon": "Zap",
        "badge": "Hook Machine",
        "avg_views": "50M - 900M+",
        "description": "Iterative attempt compilation building tension. Cuts only the final seconds of failed tries with 'ATTEMPT #...' tags, finishes with the miraculous landing, and adds an instant 0.5x slow-motion replay.",
        "difficulty": "Easy",
        "recommended_length": "15 - 40 seconds",
    },
    "myths": {
        "id": "myths",
        "name": "Mythbusters & Discoveries",
        "tagline": "5 questions tested in 60s with giant BUSTED or CONFIRMED stamps",
        "icon": "HelpCircle",
        "badge": "Massive Series Potential",
        "avg_views": "20M - 160M+",
        "description": "Rapid-fire testing of 5 community myths or questions. Free neural voice reads each myth while game audio ducks, followed by animated 3D-style BUSTED (red) or CONFIRMED (green) verdict stamps.",
        "difficulty": "Medium",
        "recommended_length": "45 - 59 seconds",
    },
    "moments": {
        "id": "moments",
        "name": "Stream & Session Moments",
        "tagline": "AI energy detector extracts the wildest, loudest clips with opening hook card",
        "icon": "Flame",
        "badge": "Auto-Cut",
        "avg_views": "5M - 600M+",
        "description": "Full gameplay or livestream session scanned for high-decibel screams, laughter, and visual motion spikes. Automatically inserts an attention-grabbing opening hook banner and word-by-word subtitles.",
        "difficulty": "Easy",
        "recommended_length": "15 - 45 seconds",
    },
    "rank": {
        "id": "rank",
        "name": "Top 5 Countdown Rankings",
        "tagline": "5 to 1 countdown with live updating on-screen leaderboard overlay",
        "icon": "Trophy",
        "badge": "Debate Trigger",
        "avg_views": "10M - 140M+",
        "description": "A 5-to-1 countdown listicle ranking weapons, stunts, police chases, or funny moments. An animated on-screen leaderboard overlay updates with each clip, revealing rank #1 at the climax.",
        "difficulty": "Easy",
        "recommended_length": "30 - 55 seconds",
    },
    "skit": {
        "id": "skit",
        "name": "Cinematic Game Skits",
        "tagline": "Shot-by-shot visual story with comic / speech bubble dialogue",
        "icon": "Clapperboard",
        "badge": "Evergreen",
        "avg_views": "20M - 400M+",
        "description": "A sound-off narrative crafted shot-by-shot using Director / Replay mode. Dialogue appears as animated comic cards or speech bubbles on screen, making it captivating even with sound muted.",
        "difficulty": "Advanced",
        "recommended_length": "25 - 50 seconds",
    },
}

class NicheVoicePreviewRequest(BaseModel):
    text: str
    voice: Optional[str] = "am_michael"
    speed: Optional[float] = 1.05

class NicheAnalyzeRequest(BaseModel):
    video_path: Optional[str] = None
    video_url: Optional[str] = None
    mode: NicheType = "commentary"
    target_duration: Optional[float] = 30.0

class NicheRenderRequest(BaseModel):
    niche: NicheType
    name: str = Field(..., min_length=1, max_length=120)
    plan: Dict[str, Any]
    output_name: Optional[str] = None
    video_url: Optional[str] = None

class NicheRenderResponse(BaseModel):
    success: bool
    task_id: str
    clip_id: str
    filename: str
    duration: float
    video_url: str
    cover_url: Optional[str] = None
    post_text: Dict[str, Any]
    qc: Dict[str, Any]
    message: str
