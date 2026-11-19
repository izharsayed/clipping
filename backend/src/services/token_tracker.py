"""Service for tracking and aggregating LLM token usage and estimated costs."""

import contextvars
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_config

logger = logging.getLogger(__name__)

# Context variable to hold user_id across async tasks
current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_user_id", default=None
)


def set_current_user_id(user_id: Optional[str]):
    """Set the active user_id in the current async context."""
    return current_user_id.set(user_id)


def get_current_user_id() -> Optional[str]:
    """Get the active user_id from the current async context."""
    return current_user_id.get()


# Pricing per 1,000,000 tokens (USD)
# Format: model_key: (input_price_per_1m, output_price_per_1m)
MODEL_PRICING: Dict[str, tuple[float, float]] = {
    # Google Gemini models
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.10, 0.40),
    "gemini-flash": (0.075, 0.30),
    "gemini-pro": (1.25, 5.00),
    # OpenAI models
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "o1-mini": (3.00, 12.00),
    "o1-preview": (15.00, 60.00),
    # Anthropic models
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    # Local Ollama
    "ollama": (0.0, 0.0),
}

DEFAULT_FALLBACK_PRICING = (0.20, 0.80)


def calculate_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated USD cost based on token counts and model pricing."""
    clean_model = model_name.lower().replace("google-gla:", "").replace("google:", "").replace("openai:", "").replace("anthropic:", "")
    
    pricing = None
    for key, price_tuple in MODEL_PRICING.items():
        if key in clean_model:
            pricing = price_tuple
            break
            
    if not pricing:
        if "ollama" in clean_model or "local" in clean_model:
            pricing = (0.0, 0.0)
        else:
            pricing = DEFAULT_FALLBACK_PRICING
            
    cost = (input_tokens / 1_000_000.0) * pricing[0] + (output_tokens / 1_000_000.0) * pricing[1]
    return round(cost, 6)


async def record_token_usage_background(
    user_id: Optional[str],
    provider: str,
    model: str,
    feature: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: Optional[int] = None,
):
    """Persist a token usage record in a standalone session."""
    if not user_id:
        return
    try:
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            service = TokenTrackerService(db)
            await service.record_usage(
                user_id=user_id,
                provider=provider,
                model=model,
                feature=feature,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
    except Exception as e:
        logger.warning("Background token recording error: %s", e)


def track_agent_run(
    result: Any,
    feature: str = "clipping",
    model_override: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """Fire-and-forget helper to track token usage from a pydantic_ai RunResult."""
    try:
        uid = user_id or get_current_user_id()
        if not uid:
            return

        usage = None
        if hasattr(result, "usage"):
            usage = result.usage() if callable(result.usage) else result.usage

        if not usage:
            return

        input_tokens = getattr(usage, "request_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "response_tokens", 0) or getattr(usage, "output_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (input_tokens + output_tokens)

        config = get_config()
        model_name = model_override or config.llm or "google-gla:gemini-1.5-flash"
        provider = "google"
        if ":" in model_name:
            provider = model_name.split(":")[0].replace("-gla", "")

        import asyncio
        asyncio.create_task(
            record_token_usage_background(
                user_id=uid,
                provider=provider,
                model=model_name,
                feature=feature,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
        )
    except Exception as e:
        logger.debug("Failed to dispatch token usage tracking: %s", e)


class TokenTrackerService:
    """Records LLM token usage events and aggregates statistics for user analytics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_usage(
        self,
        user_id: Optional[str],
        provider: str,
        model: str,
        feature: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Record an LLM token consumption event in the database."""
        if not user_id:
            logger.debug("Skipping token tracking: no user_id provided")
            return None

        total = total_tokens if total_tokens is not None else (input_tokens + output_tokens)
        cost = calculate_cost_usd(model, input_tokens, output_tokens)
        event_id = str(uuid.uuid4())

        try:
            query = text("""
                INSERT INTO api_token_usages (
                    id, user_id, provider, model, feature,
                    input_tokens, output_tokens, total_tokens, cost_usd, created_at
                ) VALUES (
                    :id, :user_id, :provider, :model, :feature,
                    :input_tokens, :output_tokens, :total_tokens, :cost_usd, NOW()
                )
            """)
            await self.db.execute(
                query,
                {
                    "id": event_id,
                    "user_id": user_id,
                    "provider": provider.lower(),
                    "model": model,
                    "feature": feature,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total,
                    "cost_usd": cost,
                },
            )
            await self.db.commit()
            return event_id
        except Exception as e:
            logger.warning("Failed to record api_token_usage: %s", e)
            await self.db.rollback()
            return None

    async def get_summary(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get aggregated token usage, timeseries, provider breakdown, and recent history."""
        config = get_config()
        active_llm = config.llm or "google-gla:gemini-1.5-flash"
        active_provider = "google"
        if ":" in active_llm:
            active_provider = active_llm.split(":")[0].replace("-gla", "")

        query_totals = text("""
            SELECT 
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
                COUNT(*) AS total_requests
            FROM api_token_usages
            WHERE user_id = :user_id
              AND created_at >= NOW() - make_interval(days => :days)
        """)
        totals_res = await self.db.execute(query_totals, {"user_id": user_id, "days": days})
        tot_row = totals_res.mappings().first()

        # Breakdown by Provider
        query_by_provider = text("""
            SELECT 
                provider,
                COALESCE(SUM(total_tokens), 0) AS tokens,
                COALESCE(SUM(cost_usd), 0.0) AS cost,
                COUNT(*) AS requests
            FROM api_token_usages
            WHERE user_id = :user_id
              AND created_at >= NOW() - make_interval(days => :days)
            GROUP BY provider
            ORDER BY tokens DESC
        """)
        prov_res = await self.db.execute(query_by_provider, {"user_id": user_id, "days": days})
        by_provider = [
            {"provider": r["provider"], "tokens": int(r["tokens"]), "cost_usd": float(r["cost"]), "requests": int(r["requests"])}
            for r in prov_res.mappings()
        ]

        # Breakdown by Feature
        query_by_feature = text("""
            SELECT 
                feature,
                COALESCE(SUM(total_tokens), 0) AS tokens,
                COALESCE(SUM(cost_usd), 0.0) AS cost,
                COUNT(*) AS requests
            FROM api_token_usages
            WHERE user_id = :user_id
              AND created_at >= NOW() - make_interval(days => :days)
            GROUP BY feature
            ORDER BY tokens DESC
        """)
        feat_res = await self.db.execute(query_by_feature, {"user_id": user_id, "days": days})
        by_feature = [
            {"feature": r["feature"], "tokens": int(r["tokens"]), "cost_usd": float(r["cost"]), "requests": int(r["requests"])}
            for r in feat_res.mappings()
        ]

        # Daily Timeseries for Charts
        query_timeseries = text("""
            SELECT 
                TO_CHAR(created_at, 'YYYY-MM-DD') AS date,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_usd), 0.0) AS cost_usd
            FROM api_token_usages
            WHERE user_id = :user_id
              AND created_at >= NOW() - make_interval(days => :days)
            GROUP BY TO_CHAR(created_at, 'YYYY-MM-DD')
            ORDER BY date ASC
        """)
        ts_res = await self.db.execute(query_timeseries, {"user_id": user_id, "days": days})
        timeseries = [
            {
                "date": r["date"],
                "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]),
                "total_tokens": int(r["total_tokens"]),
                "cost_usd": round(float(r["cost_usd"]), 4),
            }
            for r in ts_res.mappings()
        ]

        # Recent 25 events
        query_recent = text("""
            SELECT id, provider, model, feature, input_tokens, output_tokens, total_tokens, cost_usd, created_at
            FROM api_token_usages
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT 25
        """)
        rec_res = await self.db.execute(query_recent, {"user_id": user_id})
        recent_events = [
            {
                "id": r["id"],
                "provider": r["provider"],
                "model": r["model"],
                "feature": r["feature"],
                "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]),
                "total_tokens": int(r["total_tokens"]),
                "cost_usd": round(float(r["cost_usd"]), 6),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rec_res.mappings()
        ]

        return {
            "period_days": days,
            "active_provider": active_provider,
            "active_model": active_llm,
            "summary": {
                "total_tokens": int(tot_row["total_tokens"]) if tot_row else 0,
                "input_tokens": int(tot_row["input_tokens"]) if tot_row else 0,
                "output_tokens": int(tot_row["output_tokens"]) if tot_row else 0,
                "total_cost_usd": round(float(tot_row["total_cost_usd"]), 4) if tot_row else 0.0,
                "total_requests": int(tot_row["total_requests"]) if tot_row else 0,
            },
            "by_provider": by_provider,
            "by_feature": by_feature,
            "timeseries": timeseries,
            "recent_events": recent_events,
        }
