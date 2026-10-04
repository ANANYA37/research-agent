"""Authenticated watchlist endpoints."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from auth import get_current_user
from db_models import User
import watchlists as service

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


class CreateWatch(BaseModel):
    report_id: str
    frequency: Literal["weekly", "monthly"] = "weekly"


class PatchWatch(BaseModel):
    frequency: Literal["weekly", "monthly"] | None = None
    paused: bool | None = None
    mark_read: bool = False


@router.get("")
def list_items(user: User = Depends(get_current_user)):
    return service.list_watches(user.id)


@router.post("", status_code=201)
def create_item(body: CreateWatch, user: User = Depends(get_current_user)):
    try:
        return service.create_watch(user.id, body.report_id, body.frequency)
    except IntegrityError as exc:
        raise HTTPException(409, "This report is already watched. Refresh your watchlists.") from exc


@router.get("/{watch_id}")
def read_item(watch_id: str, user: User = Depends(get_current_user)):
    return service.get_watch(user.id, watch_id)


@router.patch("/{watch_id}")
def patch_item(watch_id: str, body: PatchWatch, user: User = Depends(get_current_user)):
    return service.update_watch(user.id, watch_id, body.model_dump(exclude_none=True, exclude_unset=True))


@router.delete("/{watch_id}", status_code=204)
def remove_item(watch_id: str, user: User = Depends(get_current_user)):
    service.delete_watch(user.id, watch_id)


@router.get("/{watch_id}/runs/{run_id}")
def read_run(watch_id: str, run_id: str, user: User = Depends(get_current_user)):
    return service.get_run(user.id, watch_id, run_id)


@router.post("/{watch_id}/check", status_code=202)
async def check_item(watch_id: str, user: User = Depends(get_current_user)):
    run_id = await service.start_run(user.id, watch_id)
    return {"run_id": run_id, "status": "running"}
