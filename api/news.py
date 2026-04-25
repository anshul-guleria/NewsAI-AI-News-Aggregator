from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from api.auth import get_current_user
from database.models import get_topic_id, log_user_search, get_user_history

router = APIRouter(prefix="/news", tags=["news"])


class FetchNewsRequest(BaseModel):
    topic: str


@router.post("/fetch")
async def fetch_news(req: FetchNewsRequest, current_user: dict = Depends(get_current_user)):
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    # Import here to avoid circular issues at startup and to pick up env vars
    from pipeline.graph import pipeline

    initial_state = {
        "topic": topic,
        "articles": [],
        "enriched_articles": [],
        "clustered_articles": [],
        "final_articles": [],
        "cache_hit": False,
        "error": None,
    }

    try:
        result = await run_in_threadpool(pipeline.invoke, initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    # Log search history
    tid = get_topic_id(topic)
    if tid:
        log_user_search(current_user["id"], tid)

    articles = result.get("final_articles", [])
    return {
        "topic":     topic,
        "articles":  articles,
        "cache_hit": result.get("cache_hit", False),
        "count":     len(articles),
    }


@router.get("/history")
async def history(current_user: dict = Depends(get_current_user)):
    return {"history": get_user_history(current_user["id"])}
