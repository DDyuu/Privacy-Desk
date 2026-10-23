import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_context, require_unlocked
from app.context import AppContext

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMConfig(BaseModel):
    mode: Literal["online", "ollama", "rules"] = "online"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"


def _public(config: dict) -> dict:
    return {
        "mode": config.get("mode", "rules"),
        "base_url": config.get("base_url", ""),
        "model": config.get("model", ""),
        "ollama_url": config.get("ollama_url", ""),
        "ollama_model": config.get("ollama_model", ""),
        "has_key": bool(config.get("api_key")),
    }


@router.get("/llm")
def get_llm(ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    return _public(ctx.llm_service.config())


@router.put("/llm")
def put_llm(payload: LLMConfig, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    current = ctx.llm_service.config()
    config = payload.model_dump()
    if not config["api_key"]:
        config["api_key"] = current.get("api_key", "")
    ctx.llm_service.set_config(config)
    ctx.repo.audit("settings.llm", {"mode": config["mode"]})
    return _public(config)


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
