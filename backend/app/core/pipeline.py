"""文档处理主链路：上传入库 → 识别 → 脱敏 → 校验 → 报告落库。"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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

# 白名单只收能解析成纯文本或可转 docx 的格式，避免二进制/压缩包流入解析器
ALLOWED_EXTS = {
    "txt", "md", "log", "py", "java", "js", "ts", "json", "csv", "eml", "docx", "pdf", "doc",
}

# 报告要留档模型原始返回，但长文档可能上百次调用，这里限制单块、整篇与调用条数
MAX_RAW_PER_CALL = 20000
MAX_RAW_TOTAL = 500000
MAX_LLM_CALLS = 200


def _trim_llm_trace(mode: str, calls: list[dict]) -> dict:
    """裁剪调用留档：超出预算的原始响应截断并标记，避免报告与数据库无限膨胀。"""
    trimmed: list[dict] = []
    budget = MAX_RAW_TOTAL
    truncated = len(calls) > MAX_LLM_CALLS
    for call in calls[:MAX_LLM_CALLS]:
        entry = dict(call)
        raw = str(entry.get("raw") or "")
        if len(raw) > MAX_RAW_PER_CALL:
            raw = raw[:MAX_RAW_PER_CALL] + "…（已截断）"
            truncated = True
        if len(raw) > max(budget, 0):
            raw = raw[: max(budget, 0)] + "…（已截断）"
            truncated = True
        budget -= len(raw)
        entry["raw"] = raw
        trimmed.append(entry)
    return {"mode": mode, "calls": trimmed, "truncated": truncated}


def _load_llm_trace(ctx: "AppContext", doc_id: str) -> dict:
    """读取识别阶段保存的模型调用留档；没有大模型参与时返回空字典。"""
    try:
        payload = json.loads(ctx.repo.get_text(doc_id, "llm_raw"))
    except (KeyError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def convert_doc_to_docx(source: Path, workdir: Path) -> Path:
    """借用无头 LibreOffice 把旧版 .doc 转成 docx，之后统一走 docx 解析。"""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ValueError("未检测到 LibreOffice，无法处理 .doc 文件")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", str(workdir), str(source)],
        check=True,
        capture_output=True,
        # 转换是外部进程，超时兜底防止个别文档把请求挂死
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
    # 只取文件名，剥离任何目录部分，防止 "../" 形式的路径穿越
    safe_name = Path(filename).name
    # 临时目录随 with 退出即删，持久化的只有解析文本和原始字节
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
    # 指纹记录上传的原始字节（而非转换后的 docx），便于事后核对文件来源
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
            suggest=row.get("suggest", ""),
        )
        for row in rows
    ]


def detect_document(ctx: "AppContext", doc_id: str, use_llm: bool = True) -> dict:
    text = ctx.repo.get_text(doc_id, "original")
    types = ctx.types.list()
    rule_spans = RuleEngine(types).detect(text)
    llm_spans: list[Span] = []
    mode = "rules"
    llm_trace: list[dict] = []
    if use_llm:
        llm_spans, mode, llm_trace = ctx.llm_service.detect(text, rule_spans, types)
    spans = fuse(rule_spans, llm_spans, types)
    # 识别结果挂在原文版本上，避免后续脱敏版本覆盖后检测记录错位
    version_id = ctx.repo.latest_version_id(doc_id, "original")
    ctx.repo.save_detections(doc_id, version_id, spans)
    ctx.repo.save_version(doc_id, "mode", mode)
    # 留档每块模型的原始返回（含降级失败记录），供报告导出与排障
    if llm_trace:
        ctx.repo.save_version(
            doc_id, "llm_raw", json.dumps(_trim_llm_trace(mode, llm_trace), ensure_ascii=False)
        )
    ctx.repo.update_status(doc_id, "detected")
    ctx.repo.audit("document.detect", {"doc_id": doc_id, "count": len(spans), "mode": mode})
    return {"spans": spans, "mode": mode, "text_length": len(text)}


def mask_document(
    ctx: "AppContext",
    doc_id: str,
    actions: dict[str, dict] | None = None,
    verify: bool = True,
    ignored_keys: set[str] | None = None,
) -> dict:
    document = ctx.repo.get_document(doc_id)
    if document["status"] == "uploaded":
        raise ValueError("请先执行识别，再脱敏")
    original = ctx.repo.get_text(doc_id, "original")
    all_spans = _spans_from_rows(ctx.repo.get_detections(doc_id))
    # 忽略键由「起始-结束-类型」拼成：偏移会随重新识别变化，必须与原记录一一对应
    if ignored_keys:
        all_spans = [
            replace(span, ignored=True)
            if f"{span.start}-{span.end}-{span.type_code}" in ignored_keys
            else span
            for span in all_spans
        ]
    ignored_spans = [span for span in all_spans if span.ignored]
    spans = [span for span in all_spans if not span.ignored]
    started = time.perf_counter()
    engine = MaskEngine(ctx.vault.data_key(), ctx.types, actions)
    # AAD 绑定文档 ID：加密令牌被复制到其他文档后无法解密
    result = engine.apply(original, spans, aad_prefix=doc_id)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    verify_result = None
    if verify:
        verify_result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(
            original, result.masked_text, ignored_spans
        )
        if len(spans) == 0:
            # 无实际替换时校验必然“通过”，必须显式提示，否则会被误读为已安全脱敏
            verify_result.issues.append(
                "识别结果已全部被忽略，未执行脱敏"
                if ignored_spans
                else "未识别到隐私信息，规则模式下可能存在漏检，建议启用大模型复核"
            )
    ctx.repo.save_version(doc_id, "masked", result.masked_text)
    # applied 偏移映射持久化，供 docx 变长替换导出时重映射偏移
    ctx.repo.save_version(
        doc_id, "applied", json.dumps(result.applied, ensure_ascii=False)
    )
    ctx.repo.save_version(
        doc_id,
        "ignored",
        json.dumps([span.to_dict() for span in ignored_spans], ensure_ascii=False),
    )
    stats = {
        "detected": len(all_spans),
        "applied": len(result.applied),
        "ignored": len(ignored_spans),
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
        all_spans,
        result.applied,
        verify_result,
        stats,
        llm=_load_llm_trace(ctx, doc_id),
    )
    ctx.repo.save_report(
        doc_id, job_id, "json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    )
    ctx.repo.save_report(doc_id, job_id, "pdf", build_pdf_report(report))
    status = "verified" if verify_result and verify_result.passed else "detected"
    ctx.repo.update_status(doc_id, status)
    ctx.repo.audit(
        "document.mask",
        {
            "doc_id": doc_id,
            "detected": len(all_spans),
            "applied": len(result.applied),
            "ignored": len(ignored_spans),
        },
    )
    return {
        "masked_text": result.masked_text,
        "applied": result.applied,
        "stats": stats,
        "verify": verify_result.to_dict() if verify_result else None,
        "report": report,
        "job_id": job_id,
    }


def _load_ignored_spans(ctx: "AppContext", doc_id: str) -> list[Span]:
    try:
        rows = json.loads(ctx.repo.get_text(doc_id, "ignored"))
    except (KeyError, json.JSONDecodeError):
        return []
    spans: list[Span] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            spans.append(Span(**row))
        except TypeError:
            continue
    return spans


def compare_document(ctx: "AppContext", doc_id: str) -> dict:
    original = ctx.repo.get_text(doc_id, "original")
    masked = ctx.repo.get_text(doc_id, "masked")
    try:
        applied = json.loads(ctx.repo.get_text(doc_id, "applied"))
    except KeyError:
        applied = []
    ignored_spans = _load_ignored_spans(ctx, doc_id)
    verify_result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(
        original, masked, ignored_spans
    )
    ignored = [
        f"{span.start}-{span.end}-{span.type_code}" for span in ignored_spans
    ]
    return {
        "original": original,
        "masked": masked,
        "detections": ctx.repo.get_detections(doc_id),
        "applied": applied,
        "verify": verify_result.to_dict(),
        "ignored": ignored,
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
        # AAD 必须与加密时逐字节一致（文档:类型:起始偏移），否则解密必然失败
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
    result = Verifier(ctx.types, RuleEngine(ctx.types.list())).verify(
        original, masked, _load_ignored_spans(ctx, doc_id)
    )
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
            # 截断错误信息，防止超长堆栈写满批次状态记录
            ctx.repo.update_batch_item(item_id, "failed", str(exc)[:200])

    # 并发 2 足够：链路中含外部大模型调用，并发更高易触发限流
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(run_one, item_id, item)
            for item_id, item in zip(item_ids, items)
        ]
        for future in futures:
            future.result()
    ctx.repo.finish_batch(batch_id)
