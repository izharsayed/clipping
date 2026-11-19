"""Unit tests for the 7 gaming niches: metadata, templates, drawing, and voice parsing."""
import pytest
from pathlib import Path
from PIL import Image

from src.services.niche.models import NICHE_METADATA
from src.services.niche.service import DEFAULT_PLANS
from src.services.niche import voice, draw


def test_seven_niches_metadata():
    assert len(NICHE_METADATA) == 7
    expected = ["commentary", "compare", "stunts", "myths", "moments", "rank", "skit"]
    for k in expected:
        assert k in NICHE_METADATA
        meta = NICHE_METADATA[k]
        assert "name" in meta
        assert "tagline" in meta
        assert "avg_views" in meta
        assert "description" in meta


def test_seven_niches_default_plans():
    expected = ["commentary", "compare", "stunts", "myths", "moments", "rank", "skit"]
    for k in expected:
        assert k in DEFAULT_PLANS
        assert DEFAULT_PLANS[k]["mode"] == k
        assert "post" in DEFAULT_PLANS[k]
        assert "title" in DEFAULT_PLANS[k]["post"]


def test_voice_text_cleaning_and_cues():
    raw_script = """
    # This is a note
    GTA 6 is coming soon. {pic:p1} The graphics are next level!
    [Stage note: laugh here]
    Are you excited? {pic:p2}
    """
    clean_spoken = voice.spoken(raw_script)
    assert "# This is a note" not in clean_spoken
    assert "[Stage note: laugh here]" not in clean_spoken
    assert "{pic:p1}" not in clean_spoken
    assert "{pic:p2}" not in clean_spoken
    assert "GTA 6 is coming soon." in clean_spoken

    cues = voice.extract_picture_cues(raw_script)
    assert len(cues) == 2
    assert cues[0][1] == "p1"
    assert cues[1][1] == "p2"


def test_draw_overlays():
    # Title card
    t = draw.title_card("TEST TITLE CARD", max_w=800, size=50)
    assert isinstance(t, Image.Image)
    assert t.width > 200
    assert t.height > 50

    # Pill
    p = draw.pill("TOP GAME", "2026", size=50)
    assert isinstance(p, Image.Image)

    # Attempt tag
    tag_fail = draw.attempt_tag(14, landed=False)
    tag_land = draw.attempt_tag(69, landed=True)
    assert isinstance(tag_fail, Image.Image)
    assert isinstance(tag_land, Image.Image)

    # Verdict stamp
    st = draw.stamp("BUSTED", draw.RED, size=100)
    assert isinstance(st, Image.Image)

    # Rank board
    board = draw.rank_board(
        labels={5: "Choice 5", 4: "Choice 4", 3: "Choice 3", 2: "Choice 2", 1: "Choice 1"},
        shown={5, 4},
        active_rank=4,
        total=5,
        title="Top 5 Ranking",
    )
    assert isinstance(board, Image.Image)
    assert board.size == (1080, 1920)
