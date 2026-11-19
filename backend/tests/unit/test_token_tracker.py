"""Unit tests for Token Tracker Service, cost estimation, and analytics."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.token_tracker import (
    calculate_cost_usd,
    TokenTrackerService,
    track_agent_run,
    set_current_user_id,
    get_current_user_id,
)


def test_calculate_cost_usd():
    # Gemini 1.5 Flash: $0.075 / 1M input, $0.30 / 1M output
    cost_gemini = calculate_cost_usd("gemini-1.5-flash", 1_000_000, 1_000_000)
    assert abs(cost_gemini - 0.375) < 1e-4

    # OpenAI GPT-4o-mini: $0.15 / 1M input, $0.60 / 1M output
    cost_gpt4o_mini = calculate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000)
    assert abs(cost_gpt4o_mini - 0.75) < 1e-4

    # Ollama is local, so cost is $0.00
    cost_ollama = calculate_cost_usd("ollama:llama3", 100_000, 50_000)
    assert cost_ollama == 0.0


def test_context_user_id():
    set_current_user_id("user-abc-123")
    assert get_current_user_id() == "user-abc-123"
    set_current_user_id(None)
    assert get_current_user_id() is None


@pytest.mark.asyncio
async def test_token_tracker_record_usage():
    mock_db = AsyncMock()
    service = TokenTrackerService(mock_db)

    event_id = await service.record_usage(
        user_id="user-123",
        provider="google",
        model="gemini-1.5-flash",
        feature="clipping",
        input_tokens=1500,
        output_tokens=300,
        total_tokens=1800,
    )

    assert event_id is not None
    assert mock_db.execute.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_token_tracker_get_summary():
    mock_db = AsyncMock()
    service = TokenTrackerService(mock_db)

    # Mock totals query
    mock_totals = MagicMock()
    mock_totals.mappings.return_value.first.return_value = {
        "total_tokens": 10000,
        "input_tokens": 8000,
        "output_tokens": 2000,
        "total_cost_usd": 0.0012,
        "total_requests": 5,
    }

    # Mock by provider query
    mock_prov = MagicMock()
    mock_prov.mappings.return_value = [
        {"provider": "google", "tokens": 10000, "cost": 0.0012, "requests": 5}
    ]

    # Mock by feature query
    mock_feat = MagicMock()
    mock_feat.mappings.return_value = [
        {"feature": "clipping", "tokens": 8000, "cost": 0.001, "requests": 4},
        {"feature": "post_text", "tokens": 2000, "cost": 0.0002, "requests": 1},
    ]

    # Mock timeseries query
    mock_ts = MagicMock()
    mock_ts.mappings.return_value = [
        {
            "date": "2026-11-19",
            "input_tokens": 8000,
            "output_tokens": 2000,
            "total_tokens": 10000,
            "cost_usd": 0.0012,
        }
    ]

    # Mock recent events query
    mock_recent = MagicMock()
    mock_recent.mappings.return_value = []

    mock_db.execute.side_effect = [
        mock_totals,
        mock_prov,
        mock_feat,
        mock_ts,
        mock_recent,
    ]

    summary = await service.get_summary("user-123", days=30)
    assert summary["summary"]["total_tokens"] == 10000
    assert summary["summary"]["total_cost_usd"] == 0.0012
    assert len(summary["by_provider"]) == 1
    assert len(summary["by_feature"]) == 2
    assert len(summary["timeseries"]) == 1
