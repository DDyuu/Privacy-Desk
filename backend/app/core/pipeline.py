from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.detect.fusion import fuse
from app.core.detect.rule_engine import RuleEngine, Span
from app.core.ingest.registry import load_document
from app.core.mask.engine import MaskEngine
from app.core.mask.verifier import Verifier
from app.core.report.builder import build_json_report, build_pdf_report
from app.core.security import crypto

if TYPE_CHECKING:
    from app.context import AppContext

ALLOWED_EXTS = {
    "txt", "md", "log", "py", "java", "js", "ts", "json", "csv", "eml", "docx", "pdf", "doc",
}


def convert_doc_to_docx(source: Path, workdir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ValueError("未检测到 LibreOffice，无法处理 .doc 文件")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", str(workdir), str(source)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    target = workdir / (source.stem + ".docx")
    if not target.exists():
        raise ValueError("LibreOffice 转换失败")
    return target


def create_document_from_bytes(ctx: "AppContext", filename: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"不支持的文件类型：{ext or '未知'}")
    if len(raw) > ctx.settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"文件超过 {ctx.settings.max_upload_mb}MB 限制")
    safe_name = Path(filename).name
    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)
        path = workdir / safe_name
        path.write_bytes(raw)
        if ext == "doc":
            path = convert_doc_to_docx(path, workdir)
            ext = "docx"
        try:
            model = load_document(path, ext)
        except Exception as exc:
            raise ValueError(f"文档解析失败：{exc}") from exc
        text = model.text
        source_bytes = path.read_bytes()
    doc_id = ctx.repo.create_document(
        safe_name, ext, text, hashlib.sha256(raw).hexdigest()
    )
    ctx.repo.save_blob(doc_id, "source", source_bytes)
    ctx.repo.audit("document.create", {"doc_id": doc_id, "ext": ext, "size": len(raw)})
    return doc_id


def _spans_from_rows(rows: list[dict]) -> list[Span]:
    return [
        Span(
            row["start"],
            row["end"],
            row["type_code"],
            row["text"],
            row["confidence"],
            row["source"],
            row["level"],
        )
        for row in rows
    ]


def detect_document(ctx: "AppContext", doc_id: str, use_llm: bool = True) -> dict:
    text = ctx.repo.get_text(doc_id, "original")
    types = ctx.types.list()
    rule_spans = RuleEngine(types).detect(text)
    llm_spans: list[Span] = []
    mode = "rules"
    if use_llm:
        llm_spans, mode = ctx.llm_service.detect(text, rule_spans, types)
    spans = fuse(rule_spans, llm_spans, types)
    version_id = ctx.repo.latest_version_id(doc_id, "original")
    ctx.repo.save_detections(doc_id, version_id, spans)
    ctx.repo.save_version(doc_id, "mode", mode)
    ctx.repo.update_status(doc_id, "detected")
    ctx.repo.audit("document.detect", {"doc_id": doc_id, "count": len(spans), "mode": mode})
    return {"spans": spans, "mode": mode, "text_length": len(text)}


def mask_document(
    ctx: "AppContext",
    doc_id: str,
    actions: dict[str, dict] | None = None,
    verify: bool = True,
) -> dict:
    document = ctx.repo.get_document(doc_id)
    if document["status"] == "uploaded":
        raise ValueError("请先执行识别，再脱敏")
    original = ctx.repo.get_text(doc_id, "original")
    spans = _spans_from_rows(ctx.repo.get_detections(doc_id))
    started = time.perf_counter()
    engine = MaskEngine(ctx.vault.data_key(), ctx.types, actions)
    result = engine.apply(original, spans, aad_prefix=doc_id)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    verify_result = None
    if verify:
        verify_result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(
            original, result.masked_text
        )
        if len(spans) == 0:
            verify_result.issues.append(
                "未识别到隐私信息，规则模式下可能存在漏检，建议启用大模型复核"
            )
    ctx.repo.save_version(doc_id, "masked", result.masked_text)
    # applied 偏移映射持久化，供 docx 变长替换导出时重映射偏移
    ctx.repo.save_version(
        doc_id, "applied", json.dumps(result.applied, ensure_ascii=False)
    )
    stats = {
        "detected": len(spans),
        "applied": len(result.applied),
        "mapping": result.mapping_size,
        "elapsed_ms": elapsed_ms,
    }
    job_id = ctx.repo.save_mask_job(doc_id, {"actions": actions or {}}, stats)
    try:
        actual_mode = ctx.repo.get_text(doc_id, "mode")
    except KeyError:
        actual_mode = ctx.llm_service.mode()
    report = build_json_report(
        document["name"],
        actual_mode,
        spans,
        result.applied,
        verify_result,
        stats,
    )
    ctx.repo.save_report(
        doc_id, job_id, "json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    )
    ctx.repo.save_report(doc_id, job_id, "pdf", build_pdf_report(report))
    status = "verified" if verify_result and verify_result.passed else "detected"
    ctx.repo.update_status(doc_id, status)
    ctx.repo.audit(
        "document.mask", {"doc_id": doc_id, "detected": len(spans), "applied": len(result.applied)}
    )
    return {
        "masked_text": result.masked_text,
        "applied": result.applied,
        "stats": stats,
        "verify": verify_result.to_dict() if verify_result else None,
        "report": report,
        "job_id": job_id,
    }


def compare_document(ctx: "AppContext", doc_id: str) -> dict:
    original = ctx.repo.get_text(doc_id, "original")
    masked = ctx.repo.get_text(doc_id, "masked")
    try:
        applied = json.loads(ctx.repo.get_text(doc_id, "applied"))
    except KeyError:
        applied = []
    verify_result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(original, masked)
    return {
        "original": original,
        "masked": masked,
        "detections": ctx.repo.get_detections(doc_id),
        "applied": applied,
        "verify": verify_result.to_dict(),
    }


def reveal_encrypted(ctx: "AppContext", doc_id: str) -> list[dict]:
    """解密指定文档里使用“加密”方式生成的 ENC 令牌。"""
    try:
        applied = json.loads(ctx.repo.get_text(doc_id, "applied"))
    except KeyError:
        applied = []
    key = ctx.vault.data_key()
    items: list[dict] = []
    for entry in applied:
        if entry.get("action") != "encrypt":
            continue
        token = str(entry.get("replacement") or "")
        if not token.startswith("ENC:"):
            continue
        aad = f"{doc_id}:{entry.get('type_code', '')}:{entry.get('start', 0)}".encode("utf-8")
        try:
            plain = crypto.decrypt(key, crypto.b64url_decode(token[4:]), aad).decode("utf-8")
        except Exception:
            continue
        items.append(
            {
                "token": token,
                "type_code": entry.get("type_code", ""),
                "start": entry.get("start", 0),
                "text": plain,
            }
        )
    return items


def verify_document(ctx: "AppContext", doc_id: str) -> dict:
    original = ctx.repo.get_text(doc_id, "original")
    masked = ctx.repo.get_text(doc_id, "masked")
    result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(original, masked)
    ctx.repo.update_status(doc_id, "verified" if result.passed else "masked")
    return result.to_dict()


def process_batch(
    ctx: "AppContext", batch_id: str, item_ids: list[str], items: list[tuple[str, bytes]]
) -> None:
    def run_one(item_id: str, item: tuple[str, bytes]) -> None:
        filename, raw = item
        try:
            doc_id = create_document_from_bytes(ctx, filename, raw)
            detect_document(ctx, doc_id, use_llm=True)
            mask_document(ctx, doc_id, verify=True)
            ctx.repo.update_batch_item(item_id, "done", "", doc_id)
        except Exception as exc:
            ctx.repo.update_batch_item(item_id, "failed", str(exc)[:200])

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(run_one, item_id, item)
            for item_id, item in zip(item_ids, items)
        ]
        for future in futures:
            future.result()
    ctx.repo.finish_batch(batch_id)
