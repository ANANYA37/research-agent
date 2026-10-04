"""Durable watchlist snapshots and an atomic, API-hosted scheduler."""
import asyncio
import difflib
import logging
import time
from uuid import uuid4

from sqlalchemy import select, update, func
from fastapi import HTTPException
from database import SessionLocal
from db_models import Watchlist, WatchlistRun, ResearchHistory

logger = logging.getLogger(__name__)
RUN_TIMEOUT = 900
active_tasks = set()
start_lock = asyncio.Lock()


def next_check(frequency, now):
    return now + (30 if frequency == "monthly" else 7) * 86400


def source_map(result):
    return {source.get("url"): source for source in result.get("sources", []) if source.get("url")}


def compare_versions(previous, current):
    old = [" ".join(line.split()) for line in previous.get("report", "").splitlines() if line.strip()]
    new = [" ".join(line.split()) for line in current.get("report", "").splitlines() if line.strip()]
    changes = []
    for kind, a, b, c, d in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if kind != "equal":
            changes.append({"kind": kind, "before": "\n".join(old[a:b]), "after": "\n".join(new[c:d])})
    before, after = source_map(previous), source_map(current)
    added = [after[url] for url in after.keys() - before.keys()]
    removed = [before[url] for url in before.keys() - after.keys()]
    return {"changed": bool(changes or added or removed), "text_changes": changes,
            "added_sources": added, "removed_sources": removed,
            "summary": "Report text or source list changed." if changes or added or removed else "No text or source-link changes detected.",
            "method": "Text comparison only. Rewording does not necessarily mean the evidence or conclusions changed."}


def owned(session, user_id, watch_id):
    row = session.scalar(select(Watchlist).where(Watchlist.id == watch_id, Watchlist.user_id == user_id))
    if not row:
        raise HTTPException(404, "Watchlist not found")
    return row


def summary(row):
    return {key: getattr(row, key) for key in ("id", "report_id", "topic", "depth", "frequency", "paused",
            "unread", "next_check", "last_check", "active_run_id", "created_at")}


def create_watch(user_id, report_id, frequency):
    now = time.time()
    with SessionLocal.begin() as session:
        report = session.scalar(select(ResearchHistory).where(ResearchHistory.id == report_id, ResearchHistory.user_id == user_id))
        if not report:
            raise HTTPException(404, "Report not found")
        existing = session.scalar(select(Watchlist).where(Watchlist.user_id == user_id, Watchlist.report_id == report_id))
        if existing:
            return summary(existing)
        if session.scalar(select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user_id)) >= 10:
            raise HTTPException(409, "You can watch up to 10 topics. Remove one before adding another.")
        watch = Watchlist(id=str(uuid4()), user_id=user_id, report_id=report_id, topic=report.topic,
                          depth=report.depth, frequency=frequency, paused=0, unread=0, last_check=0,
                          next_check=next_check(frequency, now), created_at=now)
        session.add(watch)
        session.flush()
        session.add(WatchlistRun(watchlist_id=watch.id, status="baseline", created_at=now, finished_at=now,
                    result={"report": report.report, "sources": report.sources or [], "queries_used": report.queries_used or []},
                    changes={}, error=""))
        return summary(watch)


def list_watches(user_id):
    with SessionLocal() as session:
        return [summary(row) for row in session.scalars(select(Watchlist).where(Watchlist.user_id == user_id).order_by(Watchlist.created_at.desc()))]


def get_watch(user_id, watch_id):
    with SessionLocal() as session:
        row = owned(session, user_id, watch_id)
        result = summary(row)
        result["runs"] = [{"id": run.id, "status": run.status, "created_at": run.created_at,
                           "finished_at": run.finished_at, "changes": run.changes, "error": run.error}
                          for run in row.runs]
        return result


def get_run(user_id, watch_id, run_id):
    with SessionLocal() as session:
        owned(session, user_id, watch_id)
        run = session.scalar(select(WatchlistRun).where(WatchlistRun.id == run_id, WatchlistRun.watchlist_id == watch_id))
        if not run:
            raise HTTPException(404, "Snapshot not found")
        return {"id": run.id, "status": run.status, "result": run.result, "created_at": run.created_at}


def update_watch(user_id, watch_id, patch):
    with SessionLocal.begin() as session:
        row = owned(session, user_id, watch_id)
        if "frequency" in patch:
            row.frequency = patch["frequency"]
            row.next_check = next_check(row.frequency, time.time())
        if "paused" in patch:
            row.paused = int(patch["paused"])
            if not row.paused:
                row.next_check = next_check(row.frequency, time.time())
        if patch.get("mark_read"):
            row.unread = 0
        session.flush()
        return summary(row)


def delete_watch(user_id, watch_id):
    with SessionLocal.begin() as session:
        row = owned(session, user_id, watch_id)
        if row.active_run_id:
            raise HTTPException(409, "Wait for the current check to finish before removing this watchlist.")
        session.delete(row)


def reserve_run(user_id, watch_id, scheduled=False):
    now = time.time()
    with SessionLocal.begin() as session:
        row = owned(session, user_id, watch_id)
        if row.active_run_id:
            raise HTTPException(409, "A check is already running.")
        if row.paused:
            raise HTTPException(409, "Resume this watchlist before checking.")
        if row.last_check and now - row.last_check < 60:
            raise HTTPException(429, "Wait a minute before checking this topic again.")
        if scheduled and row.next_check > now:
            return None
        run_id = str(uuid4())
        conditions = [Watchlist.id == watch_id, Watchlist.active_run_id.is_(None), Watchlist.paused == 0,
                      Watchlist.last_check == row.last_check]
        if scheduled:
            conditions.append(Watchlist.next_check <= now)
        result = session.execute(update(Watchlist).where(*conditions).values(
            active_run_id=run_id, last_check=now, next_check=next_check(row.frequency, now)))
        if result.rowcount != 1:
            raise HTTPException(409, "A check was already started.")
        session.add(WatchlistRun(id=run_id, watchlist_id=watch_id, status="running", created_at=now, result={}, changes={}, error=""))
        return run_id


def finish_run(watch_id, run_id, result=None, error=""):
    with SessionLocal.begin() as session:
        row = session.get(Watchlist, watch_id)
        run = session.get(WatchlistRun, run_id)
        if not row or not run or row.active_run_id != run_id or run.status != "running":
            return
        if result:
            previous = session.scalar(select(WatchlistRun).where(
                WatchlistRun.watchlist_id == watch_id, WatchlistRun.status.in_(["baseline", "success"])
            ).order_by(WatchlistRun.created_at.desc()).limit(1))
            run.result = result
            run.changes = compare_versions(previous.result if previous else {}, result)
            run.status = "success"
            row.unread = int(bool(row.unread or run.changes["changed"]))
        else:
            run.status = "failed"
            run.error = error or "The check did not return a report."
        run.finished_at = time.time()
        row.active_run_id = None


async def execute_run(watch_id, run_id):
    try:
        def load():
            with SessionLocal() as session:
                row = session.get(Watchlist, watch_id)
                return (row.topic, row.depth) if row and row.active_run_id == run_id else None
        settings = await asyncio.to_thread(load)
        if not settings:
            return
        from agent import run_research
        # Direct research bypasses history/semantic-cache shortcuts.
        result = await asyncio.wait_for(run_research(topic=settings[0], depth=settings[1]), timeout=RUN_TIMEOUT)
        if not result.get("report", "").strip():
            raise ValueError("Empty report")
        await asyncio.to_thread(finish_run, watch_id, run_id, result)
    except asyncio.CancelledError:
        await asyncio.to_thread(finish_run, watch_id, run_id, None, "Check interrupted by server shutdown. Use Check now to retry.")
        raise
    except Exception:
        logger.exception("Watchlist check failed")
        await asyncio.to_thread(finish_run, watch_id, run_id, None, "Research failed or timed out. Check the research service and try again.")


def launch_run(watch_id, run_id):
    task = asyncio.create_task(execute_run(watch_id, run_id))
    active_tasks.add(task)
    task.add_done_callback(active_tasks.discard)


async def start_run(user_id, watch_id, scheduled=False):
    # Serialize capacity checks and reservations within this API process.
    async with start_lock:
        if len(active_tasks) >= 2:
            raise HTTPException(429, "Two watchlist checks are already running. Please try again shortly.")
        run_id = await asyncio.to_thread(reserve_run, user_id, watch_id, scheduled)
        if run_id:
            launch_run(watch_id, run_id)
        return run_id


def recover_and_due():
    now = time.time()
    with SessionLocal.begin() as session:
        expired = session.scalars(select(WatchlistRun).where(
            WatchlistRun.status == "running", WatchlistRun.created_at < now - RUN_TIMEOUT - 60)).all()
        for run in expired:
            row = session.get(Watchlist, run.watchlist_id)
            if row and row.active_run_id == run.id:
                row.active_run_id = None
            run.status, run.error, run.finished_at = "failed", "Check interrupted or expired. Use Check now to retry.", now
        rows = session.scalars(select(Watchlist).where(
            Watchlist.paused == 0, Watchlist.active_run_id.is_(None), Watchlist.next_check <= now
        ).order_by(Watchlist.next_check).limit(3)).all()
        return [(row.user_id, row.id) for row in rows]


async def scheduler_loop():
    try:
        while True:
            try:
                for user_id, watch_id in await asyncio.to_thread(recover_and_due):
                    if len(active_tasks) >= 2:
                        break
                    try:
                        await start_run(user_id, watch_id, True)
                    except HTTPException:
                        pass
            except Exception:
                logger.exception("Watchlist scheduler iteration failed")
            await asyncio.sleep(60)
    finally:
        tasks = list(active_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
