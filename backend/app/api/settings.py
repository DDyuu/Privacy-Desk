import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_context, require_unlocked
from app.context import AppContext
from app.llm.client import probe_ollama
from app.llm.env_keys import normalize_names

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMConfig(BaseModel):
    mode: Literal["online", "ollama", "rules"] = "online"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-flash"
    api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    env_key_names: list[str] = Field(default_factory=list)


def _public(ctx: AppContext, names: list[str] | None = None, source: str | None = None) -> dict:
    config = ctx.llm_service.config()
    key_source = ctx.llm_service.key_source() if source is None else source
    return {
        "mode": config.get("mode", "rules"),
        "base_url": config.get("base_url", ""),
        "model": config.get("model", ""),
        "ollama_url": config.get("ollama_url", ""),
        "ollama_model": config.get("ollama_model", ""),
        "has_key": bool(config.get("api_key")) if source is None else source != "none",
        "key_source": key_source,
        "env_keys": ctx.llm_service.env_key_candidates(names, key_source),
        "env_key_names": ctx.llm_service.env_key_names(),
    }


@router.get("/llm")
def get_llm(ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    return _public(ctx)


@router.get("/llm/env-keys")
def detect_env_keys(names: str | None = None, ctx: AppContext = Depends(get_context)) -> dict:
    """按当前表单中的变量名即时扫描环境变量（names 为空时只扫描内置变量）。"""
    require_unlocked(ctx)
    parsed = None if names is None else [name for name in names.split(",") if name.strip()]
    custom = parsed or []
    return _public(ctx, custom, ctx.llm_service.preview_key_source(custom))


@router.put("/llm")
def put_llm(payload: LLMConfig, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    config = payload.model_dump()
    if not config["api_key"]:
        # 只继承已落库的 Key，避免把环境变量里的 Key 复制进数据库
        config["api_key"] = ctx.llm_service.stored_api_key()
    config["env_key_names"] = normalize_names(config["env_key_names"])
    ctx.llm_service.set_config(config)
    ctx.repo.audit("settings.llm", {"mode": config["mode"]})
    return _public(ctx)


@router.get("/ollama/status")
def ollama_status(
    url: str | None = None,
    model: str | None = None,
    ctx: AppContext = Depends(get_context),
) -> dict:
    """检测 Ollama 服务连通性；url/model 缺省时使用已保存配置。"""
    require_unlocked(ctx)
    config = ctx.llm_service.config()
    target = url if url is not None else config.get("ollama_url", "")
    target_model = model if model is not None else config.get("ollama_model", "")
    result = probe_ollama(str(target), str(target_model))
    result["url"] = str(target)
    return result


@router.post("/llm/test")
def test_llm(ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    mode = ctx.llm_service.mode()
    if mode == "rules":
        return {"ok": False, "mode": "rules", "message": "未配置在线或本地模型"}
    client = ctx.llm_service.build_client()
    started = time.perf_counter()
    try:
        items = client.extract(
            "这是一段连通性测试文本，请返回空数组。",
            [{"code": "NAME_CN", "name": "姓名", "hint": "中文人名"}],
        )
    except Exception as exc:
        raise HTTPException(502, f"模型调用失败：{exc}") from exc
    return {
        "ok": True,
        "mode": mode,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "items": len(items),
    }
