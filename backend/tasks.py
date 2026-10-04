"""Celery tasks for long-running research."""

import asyncio

from agent import run_research_streaming
from celery_app import celery_app
from history import save_research


async def _run_streaming_task(task, user_id: str, topic: str, depth: int, visual_planner: bool = False) -> dict:
    final_result = None
    async for event in run_research_streaming(topic=topic, depth=depth, visual_planner=visual_planner):
        if event["type"] == "status":
            task.update_state(state="PROGRESS", meta=event["data"])
        elif event["type"] == "result":
            final_result = event["data"]

    if final_result is None:
        raise RuntimeError("Research completed without producing a result")

    saved_item = save_research(user_id, topic, depth, final_result)
    final_result["history_id"] = saved_item["id"]
    final_result["from_cache"] = False
    return final_result


if celery_app:

    @celery_app.task(bind=True, name="research.run")
    def run_research_task(self, user_id: str, topic: str, depth: int, visual_planner: bool = False) -> dict:
        self.update_state(
            state="STARTED",
            meta={"step": "queued", "detail": "Research worker started", "progress": 0},
        )
        return asyncio.run(_run_streaming_task(self, user_id, topic, depth, visual_planner))
