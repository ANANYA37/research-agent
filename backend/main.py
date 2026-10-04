"""FastAPI application — entry point for the research agent API."""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from uuid import uuid4
from dotenv import load_dotenv

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from celery_app import celery_app
from exports import export_report
from freshness import should_use_cache
from auth import create_access_token, get_current_user, get_db, hash_password, verify_password
from database import init_db
from db_models import User
from llm_provider import get_provider_name, get_required_api_key_name
from models import (
    ResearchHistoryItem,
    ResearchHistorySummary,
    ResearchRequest,
    ResearchResponse,
    HealthResponse,
    SourceInfo,
    AuthResponse,
    CollectionCreateRequest,
    LoginRequest,
    RegisterRequest,
    ReportMetadataRequest,
    TagCreateRequest,
    UserResponse,
)
from agent import run_research, run_research_streaming, llm as rate_limited_llm
from history import (
    assign_report_metadata,
    create_collection,
    create_tag,
    find_cached_research,
    get_history_item,
    list_collections,
    list_history,
    list_tags,
    save_research,
)

if celery_app:
    from tasks import run_research_task

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

LOCAL_TASKS: dict[str, dict] = {}
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


def _cleanup_local_tasks():
    now = datetime.now(timezone.utc)
    expired = []
    for t_id, t in LOCAL_TASKS.items():
        if t.get("status") in ("SUCCESS", "FAILURE"):
            if "updated_at" in t:
                try:
                    updated = datetime.fromisoformat(t["updated_at"])
                    if (now - updated).total_seconds() > 3600:
                        expired.append(t_id)
                except Exception:
                    pass
    for t_id in expired:
        del LOCAL_TASKS[t_id]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_local_research_task(task_id: str, user_id: str, topic: str, depth: int, visual_planner: bool = False):
    """Run background research in-process when Celery/Redis is unavailable."""
    try:
        LOCAL_TASKS[task_id].update({
            "status": "STARTED",
            "meta": {
                "step": "queued",
                "detail": "Research started in local background mode",
                "progress": 0.05,
                "iteration": 1,
            },
            "updated_at": _now_iso(),
        })

        final_result = None
        async for event in run_research_streaming(topic=topic, depth=depth, visual_planner=visual_planner):
            if event["type"] == "status":
                LOCAL_TASKS[task_id].update({
                    "status": "PROGRESS",
                    "meta": event["data"],
                    "updated_at": _now_iso(),
                })
            elif event["type"] == "result":
                final_result = event["data"]

        if final_result is None:
            raise RuntimeError("Research completed without producing a result")

        saved_item = await asyncio.to_thread(save_research, user_id, topic, depth, final_result)
        final_result["history_id"] = saved_item["id"]
        final_result["from_cache"] = False
        LOCAL_TASKS[task_id].update({
            "status": "SUCCESS",
            "result": final_result,
            "meta": {
                "step": "done",
                "detail": "Research complete",
                "progress": 1,
                "iteration": final_result.get("iterations_completed", 0),
            },
            "updated_at": _now_iso(),
        })
    except Exception as exc:
        LOCAL_TASKS[task_id].update({
            "status": "FAILURE",
            "error": str(exc),
            "updated_at": _now_iso(),
        })


from watchlist_routes import router as watchlist_router
from watchlists import scheduler_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    init_db()
    if os.getenv("JWT_SECRET_KEY") is None:
        logger.warning("JWT_SECRET_KEY is not set; configure a random value before deployment.")
    provider = get_provider_name()
    api_key_name = get_required_api_key_name(provider)
    if api_key_name and not os.getenv(api_key_name):
        logger.warning(f"{api_key_name} not set for LLM_PROVIDER={provider}!")
    if not os.getenv("TAVILY_API_KEY"):
        logger.warning("TAVILY_API_KEY not set in environment!")
    if not celery_app:
        logger.warning("Celery is unavailable. Durable background tasks are disabled.")
    logger.info(f"Research Agent API started with LLM provider: {provider}")
    scheduler = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        scheduler.cancel()
        await asyncio.gather(scheduler, return_exceptions=True)
        logger.info("Research Agent API shutting down")


app = FastAPI(
    title="AI Research Agent",
    description="An autonomous research agent that searches, reads, and synthesizes web content into structured reports.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(watchlist_router)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse()


@app.post("/api/auth/register", response_model=AuthResponse)
@limiter.limit("10/minute")
async def register(request: Request, payload: RegisterRequest, db=Depends(get_db)):
    """Create an account and return a signed bearer token."""
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account already exists for this email") from exc
    db.refresh(user)
    return AuthResponse(access_token=create_access_token(user), user=UserResponse(id=user.id, email=user.email))


@app.post("/api/auth/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, db=Depends(get_db)):
    """Authenticate an account without exposing whether an email exists."""
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return AuthResponse(access_token=create_access_token(user), user=UserResponse(id=user.id, email=user.email))


@app.get("/api/auth/me", response_model=UserResponse)
async def current_account(current_user: User = Depends(get_current_user)):
    return UserResponse(id=current_user.id, email=current_user.email)


@app.get("/api/rate-limit-stats")
async def rate_limit_stats():
    """Monitor rate limiter and cache stats — useful for production debugging."""
    return {
        "cache": getattr(rate_limited_llm, "cache_stats", {}),
        "consecutive_429s": getattr(rate_limited_llm, "_consecutive_429s", 0),
        "status": "healthy" if getattr(rate_limited_llm, "_consecutive_429s", 0) < 3 else "degraded",
    }


@app.get("/api/config")
async def app_config():
    """Return runtime feature configuration for the frontend."""
    return {
        "llm_provider": get_provider_name(),
        "queue_enabled": True,
        "queue_mode": "celery" if celery_app else "local",
        "semantic_cache": True,
        "freshness_detection": True,
    }


def _history_response(item: dict, from_cache: bool = True) -> ResearchResponse:
    return ResearchResponse(
        report=item.get("report", ""),
        sources=[SourceInfo(**s) for s in item.get("sources", [])],
        queries_used=item.get("queries_used", []),
        iterations_completed=item.get("iterations_completed", 0),
        history_id=item.get("id"),
        from_cache=from_cache,
        citation_verification=item.get("citation_verification", {}),
    )


@app.get("/api/history", response_model=list[ResearchHistorySummary])
async def get_history(current_user: User = Depends(get_current_user)):
    """Return saved research history, newest first."""
    return [
        ResearchHistorySummary(
            id=item["id"],
            topic=item["topic"],
            depth=item["depth"],
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            queries_used=item.get("queries_used", []),
            iterations_completed=item.get("iterations_completed", 0),
            sources_count=len(item.get("sources", [])),
            collections=item.get("collections", []),
            tags=item.get("tags", []),
        )
        for item in (await asyncio.to_thread(list_history, current_user.id))
    ]


@app.get("/api/history/{item_id}", response_model=ResearchHistoryItem)
async def get_history_detail(item_id: str, current_user: User = Depends(get_current_user)):
    """Return a saved research result."""
    item = await asyncio.to_thread(get_history_item, current_user.id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")

    return ResearchHistoryItem(
        id=item["id"],
        topic=item["topic"],
        depth=item["depth"],
        created_at=item["created_at"],
        updated_at=item["updated_at"],
        report=item.get("report", ""),
        sources=[SourceInfo(**s) for s in item.get("sources", [])],
        queries_used=item.get("queries_used", []),
        iterations_completed=item.get("iterations_completed", 0),
        history_id=item["id"],
        from_cache=True,
    )


@app.post("/api/research", response_model=ResearchResponse)
@limiter.limit("15/hour")
async def start_research(request: Request, payload: ResearchRequest, current_user: User = Depends(get_current_user)):
    """
    Start a research session (non-streaming).
    
    Runs the full agent loop and returns the final report.
    """
    if not payload.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    try:
        logger.info(f"  [API] Research request: topic='{payload.topic}', depth={payload.depth}, visual_planner={payload.visual_planner}")
        
        use_cache = should_use_cache(payload.topic, payload.force_fresh)
        cached = await asyncio.to_thread(find_cached_research, current_user.id, payload.topic.strip(), payload.depth) if use_cache else None
        
        # If visual_planner is requested, but cached report has no diagrams, bypass cache
        if cached and payload.visual_planner and "```mermaid" not in cached.get("report", ""):
            logger.info(f"  [API] Bypassing cache for topic '{payload.topic}' because diagrams were requested but missing in cache.")
            cached = None

        if cached:
            logger.info(f"  [API] Cache hit for topic '{payload.topic}'")
            return _history_response(cached, from_cache=True)
        
        logger.info(f"  [API] Running fresh research for topic '{payload.topic}'...")
        result = await run_research(
            topic=payload.topic.strip(),
            depth=payload.depth,
            visual_planner=payload.visual_planner,
        )
        saved_item = await asyncio.to_thread(save_research, current_user.id, payload.topic.strip(), payload.depth, result)
        
        return ResearchResponse(
            report=result["report"],
            sources=[SourceInfo(**s) for s in result["sources"]],
            queries_used=result["queries_used"],
            iterations_completed=result["iterations_completed"],
            history_id=saved_item["id"],
            from_cache=False,
            citation_verification=result.get("citation_verification", {}),
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")


@app.post("/api/research/stream")
@limiter.limit("15/hour")
async def start_research_stream(request: Request, payload: ResearchRequest, current_user: User = Depends(get_current_user)):
    """
    Start a research session with SSE streaming.
    
    Streams status updates as the agent progresses, then sends the final report.
    """
    if not payload.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    use_cache = should_use_cache(payload.topic, payload.force_fresh)
    cached = await asyncio.to_thread(find_cached_research, current_user.id, payload.topic.strip(), payload.depth) if use_cache else None
    
    # Bypass cache when diagrams are requested but missing from the cached report
    if cached and payload.visual_planner and "```mermaid" not in cached.get("report", ""):
        cached = None
    
    api_key_name = get_required_api_key_name()
    if (api_key_name and not os.getenv(api_key_name)) or not os.getenv("TAVILY_API_KEY"):
        if not cached:
            raise HTTPException(
                status_code=500,
                detail=f"API keys not configured. Set {api_key_name or 'provider config'} and TAVILY_API_KEY in .env file."
            )
    
    async def event_generator():
        try:
            if cached:
                detail = "Loaded saved research from history"
                yield {
                    "event": "status",
                    "data": json.dumps({
                        "step": "done",
                        "detail": detail,
                        "progress": 1,
                        "iteration": cached.get("iterations_completed", 0),
                    }),
                }
                yield {
                    "event": "result",
                    "data": json.dumps(_history_response(cached, from_cache=True).model_dump()),
                }
                yield {
                    "event": "done",
                    "data": json.dumps({"message": "Research loaded from history"}),
                }
                return

            async for event in run_research_streaming(
                topic=payload.topic.strip(),
                depth=payload.depth,
                visual_planner=payload.visual_planner,
            ):
                if event["type"] == "result":
                    saved_item = await asyncio.to_thread(save_research, current_user.id, payload.topic.strip(), payload.depth, event["data"])
                    event["data"]["history_id"] = saved_item["id"]
                    event["data"]["from_cache"] = False

                yield {
                    "event": event["type"],
                    "data": json.dumps(event["data"]),
                }
            
            # Send completion event
            yield {
                "event": "done",
                "data": json.dumps({"message": "Research complete"}),
            }
        
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }
    
    return EventSourceResponse(event_generator())


@app.post("/api/research/task")
@limiter.limit("15/hour")
async def queue_research_task(request: Request, payload: ResearchRequest, current_user: User = Depends(get_current_user)):
    """Queue durable research in Celery + Redis and return a task id."""
    if not payload.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    logger.info(f"  [TASK] Research task: topic='{payload.topic}', depth={payload.depth}, visual_planner={payload.visual_planner}")

    use_cache = should_use_cache(payload.topic, payload.force_fresh)
    cached = await asyncio.to_thread(find_cached_research, current_user.id, payload.topic.strip(), payload.depth) if use_cache else None

    # Bypass cache when diagrams are requested but missing from the cached report
    if cached and payload.visual_planner and "```mermaid" not in cached.get("report", ""):
        logger.info(f"  [TASK] Bypassing cache — diagrams requested but not found in cached report")
        cached = None

    if cached:
        logger.info(f"  [TASK] Cache hit for topic '{payload.topic}'")
        return {
            "status": "SUCCESS",
            "from_cache": True,
            "result": _history_response(cached, from_cache=True).model_dump(),
        }

    if not celery_app:
        _cleanup_local_tasks()
        task_id = str(uuid4())
        LOCAL_TASKS[task_id] = {
            "task_id": task_id,
            "user_id": current_user.id,
            "topic": payload.topic.strip(),
            "depth": payload.depth,
            "status": "PENDING",
            "meta": {
                "step": "queued",
                "detail": "Research queued locally",
                "progress": 0,
                "iteration": 0,
            },
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        asyncio.create_task(_run_local_research_task(
            task_id, current_user.id, payload.topic.strip(), payload.depth, visual_planner=payload.visual_planner
        ))
        return {"task_id": task_id, "status": "PENDING", "local": True}

    task = run_research_task.delay(current_user.id, payload.topic.strip(), payload.depth, payload.visual_planner)
    return {"task_id": task.id, "status": "PENDING"}


@app.get("/api/research/task/{task_id}")
async def get_research_task(task_id: str, current_user: User = Depends(get_current_user)):
    """Return Celery task state and final result when complete."""
    if not celery_app:
        task = LOCAL_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Background task not found.")
        if task.get("user_id") != current_user.id:
            raise HTTPException(status_code=404, detail="Background task not found.")
        return task

    task_result = celery_app.AsyncResult(task_id)
    payload = {
        "task_id": task_id,
        "status": task_result.status,
        "meta": task_result.info if isinstance(task_result.info, dict) else {},
    }

    if task_result.successful():
        payload["result"] = task_result.result
    elif task_result.failed():
        payload["error"] = str(task_result.info)

    return payload


@app.post("/api/history/{item_id}/evidence")
@limiter.limit("6/hour")
async def review_history_evidence(request: Request, item_id: str, current_user: User = Depends(get_current_user)):
    """Review only an authenticated user's saved report and snippets."""
    from evidence import analyze_evidence

    item = await asyncio.to_thread(get_history_item, current_user.id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    try:
        return await analyze_evidence(item, rate_limited_llm)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Evidence review timed out. Please try again later.") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="The model could not produce a grounded review. Try again or collect more source evidence.") from exc
    except Exception as exc:
        logger.warning("Evidence review unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Evidence review is temporarily unavailable. Please try again later.") from exc


@app.get("/api/history/{item_id}/export/{export_format}")
async def export_history_item(item_id: str, export_format: str, current_user: User = Depends(get_current_user)):
    """Export a saved report as Markdown, PDF, or DOCX."""
    item = await asyncio.to_thread(get_history_item, current_user.id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")

    try:
        data, media_type, extension = export_report(item.get("report", ""), export_format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    filename = f"research-report-{item_id}.{extension}"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/collections")
async def get_collections(current_user: User = Depends(get_current_user)):
    return await asyncio.to_thread(list_collections, current_user.id)


@app.post("/api/collections")
async def add_collection(payload: CollectionCreateRequest, current_user: User = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(create_collection, current_user.id, payload.name, payload.description)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A collection with this name already exists") from exc


@app.get("/api/tags")
async def get_tags(current_user: User = Depends(get_current_user)):
    return await asyncio.to_thread(list_tags, current_user.id)


@app.post("/api/tags")
async def add_tag(payload: TagCreateRequest, current_user: User = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(create_tag, current_user.id, payload.name, payload.color)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A tag with this name already exists") from exc


@app.put("/api/history/{item_id}/metadata")
async def update_report_metadata(
    item_id: str,
    payload: ReportMetadataRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        item = await asyncio.to_thread(
            assign_report_metadata, current_user.id, item_id, payload.collection_ids, payload.tag_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    return item


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)
