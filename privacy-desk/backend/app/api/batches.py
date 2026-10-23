from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.api.deps import get_context, require_unlocked
from app.context import AppContext
from app.core import pipeline

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("")
async def create_batch(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    ctx: AppContext = Depends(get_context),
) -> dict:
    require_unlocked(ctx)
    if not files:
        raise HTTPException(400, "请选择文件")
    payload = [(file.filename or "upload.txt", await file.read()) for file in files]
    batch_id = ctx.repo.create_batch(len(payload))
    item_ids = [ctx.repo.add_batch_item(batch_id) for _ in payload]
    background.add_task(pipeline.process_batch, ctx, batch_id, item_ids, payload)
    return {"id": batch_id, "total": len(payload)}


@router.get("/{batch_id}")
def get_batch(batch_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        return ctx.repo.get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(404, "批量任务不存在") from exc
