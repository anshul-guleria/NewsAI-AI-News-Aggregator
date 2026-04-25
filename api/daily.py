from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from api.auth import get_current_user
from database.models import (
    PREDEFINED_TOPICS,
    TOPIC_EMOJIS,
    get_user_subscriptions,
    set_user_subscriptions,
)

router = APIRouter(prefix="/daily", tags=["daily"])


class SubscriptionRequest(BaseModel):
    topics: list[str]

@router.get("/topics")
async def list_topics():
    """Return all predefined topics with their emoji labels."""
    return {
        "topics": [
            {"topic": t, "emoji": TOPIC_EMOJIS.get(t, "📰")}
            for t in PREDEFINED_TOPICS
        ]
    }


@router.get("/subscriptions")
async def get_subscriptions(current_user: dict = Depends(get_current_user)):
    """Return the current user's subscribed topics."""
    topics = get_user_subscriptions(current_user["id"])
    return {"subscriptions": topics}


@router.put("/subscriptions")
async def update_subscriptions(
    req: SubscriptionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Replace the user's full subscription list atomically."""
    invalid = [t for t in req.topics if t not in PREDEFINED_TOPICS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown topics: {invalid}")

    set_user_subscriptions(current_user["id"], req.topics)
    return {
        "subscriptions": req.topics,
        "count": len(req.topics),
        "message": f"Subscribed to {len(req.topics)} topic(s)",
    }


@router.post("/run")
async def trigger_digest(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger the daily digest pipeline.
    Output is printed to the server terminal.
    """
    from scheduler.daily_digest import run_daily_digest
    await run_in_threadpool(run_daily_digest)
    return {"message": "Daily digest complete — check the FastAPI server terminal for output."}
