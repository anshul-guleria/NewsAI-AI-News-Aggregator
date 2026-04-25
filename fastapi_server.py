from dotenv import load_dotenv
load_dotenv()  # must be first — all modules that follow may read env vars

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from database.db import init_db
from api.auth  import router as auth_router
from api.news  import router as news_router
from api.daily import router as daily_router

app = FastAPI(
    title="AI News Aggregator API",
    description="Multi-user news aggregation powered by LangGraph",
    version="1.0.0",
)

# Allow Flask frontend (port 5000) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(news_router)
app.include_router(daily_router)

# ---------------------------------------------------------------------------
# Background scheduler — daily digest at 08:00 UTC every day
# ---------------------------------------------------------------------------
_scheduler = BackgroundScheduler(timezone="UTC")


@app.on_event("startup")
async def startup():
    init_db()

    from scheduler.daily_digest import run_daily_digest
    _scheduler.add_job(
        run_daily_digest,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_digest",
        replace_existing=True,
    )
    _scheduler.start()

    print("[FastAPI] Ready — API docs at http://localhost:8000/docs")
    print("[Scheduler] Daily digest scheduled at 08:00 UTC every day")


@app.on_event("shutdown")
async def shutdown():
    _scheduler.shutdown(wait=False)


@app.get("/")
async def root():
    return {"message": "AI News Aggregator API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapi_server:app", host="0.0.0.0", port=8000, reload=True)
