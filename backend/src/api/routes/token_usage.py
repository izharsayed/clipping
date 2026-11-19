"""Routes for viewing AI token and API usage analytics."""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth_headers import get_authenticated_user_id
from ...config import get_config
from ...database import get_db
from ...services.token_tracker import TokenTrackerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/token-usage", tags=["token-usage"])


@router.get("/summary", response_model=Dict[str, Any])
async def get_token_usage_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated token metrics, costs, timeseries, and provider breakdown for the user."""
    user_id = get_authenticated_user_id(request, get_config())
    service = TokenTrackerService(db)
    summary = await service.get_summary(user_id=user_id, days=days)
    return summary
