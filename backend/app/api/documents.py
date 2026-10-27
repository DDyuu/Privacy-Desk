"""文档接口：上传、识别、脱敏、对比、导出与 ENC 令牌解密。"""

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.api.deps import get_context, require_unlocked, verify_password
from app.context import AppContext
from app.core import pipeline
from app.core.ingest.docx_loader import load_docx
from app.core.ingest.registry import export_document
from app.core.ingest.writer import write_pdf

router = APIRouter(prefix="/documents", tags=["documents"])


class DetectIn(BaseModel):
    use_llm: bool = True


class MaskIn(BaseModel):
    actions: dict[str, dict] = {}
    verify: bool = True
    ignored: list[str] = []


class EditIn(BaseModel):
    text: str


class RevealIn(BaseModel):
    password: str | None = None


def _not_found() -> HTTPException:
    return HTTPException(404, "文档不存在")


@router.post("")
async def upload(
    file: UploadFile = File(...), ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    # 单机数据库会随文档增长，先用总数限制挡住无限上传，再谈单文件大小
    if ctx.repo.count_documents() >= ctx.settings.max_docs:
        raise HTTPException(
            409, f"文档数量已达上限（{ctx.settings.max_docs}），请先清理历史文档"
        )
    raw = await file.read()
    try:
        doc_id = pipeline.create_document_from_bytes(ctx, file.filename or "upload.txt", raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ctx.repo.get_document(doc_id)


@router.delete("")
def clear_documents(ctx: AppContext = Depends(get_context)) -> dict:
    """清空全部历史文档及其识别、脱敏和报告数据。"""
    require_unlocked(ctx)
    deleted = ctx.repo.delete_all_documents()
    ctx.repo.audit("document.clear", {"deleted": deleted})
    return {"deleted": deleted}


@router.get("")
def list_documents(ctx: AppContext = Depends(get_context)) -> list[dict]:
    require_unlocked(ctx)
    return ctx.repo.list_documents()


@router.get("/{doc_id}")
def get_document(doc_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        document = ctx.repo.get_document(doc_id)
        document["text"] = ctx.repo.get_text(doc_id, "original")
        document["detections"] = ctx.repo.get_detections(doc_id)
        return document
    except KeyError as exc:
        raise _not_found() from exc


@router.put("/{doc_id}/content")
def edit_content(
    doc_id: str, payload: EditIn, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    try:
        ctx.repo.get_document(doc_id)
    except KeyError as exc:
        raise _not_found() from exc
    ctx.repo.save_version(doc_id, "original", payload.text)
    ctx.repo.clear_detections(doc_id)
    ctx.repo.update_status(doc_id, "uploaded")
    return {"id": doc_id, "length": len(payload.text)}


@router.post("/{doc_id}/detect")
def detect(
    doc_id: str, payload: DetectIn, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    try:
        result = pipeline.detect_document(ctx, doc_id, payload.use_llm)
    except KeyError as exc:
        raise _not_found() from exc
    return {
        "spans": [span.to_dict() for span in result["spans"]],
        "mode": result["mode"],
        "text_length": result["text_length"],
    }


@router.post("/{doc_id}/mask")
def mask(
    doc_id: str, payload: MaskIn, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    try:
        result = pipeline.mask_document(
            ctx, doc_id, payload.actions, payload.verify, set(payload.ignored)
        )
    except KeyError as exc:
        raise _not_found() from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "masked_text": result["masked_text"],
        "applied": result["applied"],
        "stats": result["stats"],
        "verify": result["verify"],
        "job_id": result["job_id"],
        "summary": result["report"]["summary"],
    }


@router.post("/{doc_id}/verify")
def verify(doc_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        return pipeline.verify_document(ctx, doc_id)
    except KeyError as exc:
        raise HTTPException(404, "文档或脱敏结果不存在") from exc


@router.get("/{doc_id}/compare")
def compare(doc_id: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        return pipeline.compare_document(ctx, doc_id)
    except KeyError as exc:
        raise HTTPException(404, "文档或脱敏结果不存在") from exc


@router.post("/{doc_id}/reveal")
def reveal(
    doc_id: str, payload: RevealIn, ctx: AppContext = Depends(get_context)
) -> dict:
    """解密该文档中以“加密”方式处理的 ENC 令牌，需再次校验主密码。"""
    require_unlocked(ctx)
    # ENC 令牌能还原出原始隐私值，敏感度等同明文，因此即使会话已解锁也要重新验密
    verify_password(ctx, payload.password, "解密 ENC 令牌")
    try:
        document = ctx.repo.get_document(doc_id)
    except KeyError as exc:
        raise _not_found() from exc
    if document["status"] in {"uploaded", "detected"}:
        raise HTTPException(409, "尚未完成脱敏")
    items = pipeline.reveal_encrypted(ctx, doc_id)
    ctx.repo.audit("document.reveal", {"doc_id": doc_id, "count": len(items)})
    return {"items": items}


@router.get("/{doc_id}/export")
def export(
    doc_id: str,
    kind: str = "masked",
    fmt: str = "auto",
    password: str | None = None,
    ctx: AppContext = Depends(get_context),
):
    require_unlocked(ctx)
    try:
        document = ctx.repo.get_document(doc_id)
        if kind not in {"masked", "report"}:
            raise HTTPException(400, "不支持的导出类型")
        if kind == "report":
            if document["status"] == "uploaded":
                raise HTTPException(409, "报告已过期，请重新识别并脱敏")
            # 报告包含识别与替换明细，导出前需再次校验主密码
            verify_password(ctx, password)
            report_format = "pdf" if fmt == "pdf" else "json"
            payload = ctx.repo.latest_report(doc_id, report_format)
            media = "application/pdf" if report_format == "pdf" else "application/json"
            return Response(
                payload,
                media_type=media,
                headers={
                    "Content-Disposition": f'attachment; filename="report.{report_format}"'
                },
            )
        # 脱敏文本里只剩掩码或 ENC 令牌，不含原文，因此导出掩码文件不再二次验密
        if document["status"] in {"uploaded", "detected"}:
            raise HTTPException(409, "尚未完成有效脱敏，禁止导出")
        if fmt not in {"auto", document["ext"]}:
            raise HTTPException(400, "仅支持按原格式导出")
        masked = ctx.repo.get_text(doc_id, "masked")
        ext = document["ext"] if fmt == "auto" else fmt
        # 导出文件放独立临时目录：不在数据目录留下明文副本，
        # 也不与并发导出互相覆盖。
        workdir = Path(tempfile.mkdtemp())
        target = workdir / f"masked.{ext}"
        if ext == "docx":
            source_path = workdir / "source.docx"
            source_path.write_bytes(ctx.repo.get_blob(doc_id, "source"))
            try:
                applied = json.loads(ctx.repo.get_text(doc_id, "applied"))
            except KeyError:
                applied = None
            export_document(load_docx(source_path), masked, target, "docx", applied=applied)
        elif ext == "pdf":
            write_pdf(masked, target)
        else:
            target.write_text(masked, encoding="utf-8")
        return FileResponse(
            target,
            filename=f"masked.{ext}",
            # 响应体发送完后才删临时目录，避免文件还在传输时就被清理
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )
    except KeyError as exc:
        raise HTTPException(404, "文档或导出结果不存在") from exc
