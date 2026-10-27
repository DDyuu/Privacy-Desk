"""批量上传接口：先落库批次与条目，再由后台任务逐份识别与脱敏，前端轮询进度。"""

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
    """创建批次并立即返回；识别与脱敏在响应发送后由后台任务执行。"""
    require_unlocked(ctx)
    if not files:
        raise HTTPException(400, "请选择文件")
    # 先检查总量再读文件，避免超限时仍把整批内容读进内存
    if ctx.repo.count_documents() + len(files) > ctx.settings.max_docs:
        raise HTTPException(
            409, f"文档数量将超过上限（{ctx.settings.max_docs}），请先清理历史文档"
        )
    # UploadFile 的生命周期只到本次请求结束，必须在请求内读完内容再交给后台任务
    payload = [(file.filename or "upload.txt", await file.read()) for file in files]
    batch_id = ctx.repo.create_batch(len(payload))
    item_ids = [ctx.repo.add_batch_item(batch_id) for _ in payload]
    # 批量处理耗时远超一次 HTTP 请求，用 BackgroundTasks 先响应批次号；
    # 真正的并行在 pipeline.process_batch 的线程池里完成，状态已落库供轮询。
    background.add_task(pipeline.process_batch, ctx, batch_id, item_ids, payload)
    return {"id": batch_id, "total": len(payload)}


@router.get("/{batch_id}")
def get_batch(batch_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        return ctx.repo.get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(404, "批量任务不存在") from exc
