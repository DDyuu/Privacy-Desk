"""会话接口：首次设置主密码、解锁/锁定，以及解锁失败时的退避。"""

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_context
from app.context import AppContext
from app.core.security import keys

router = APIRouter(prefix="/session", tags=["session"])
# 进程内失败计数（按 app 实例隔离），只用于本地退避，重启即清零，不落库
_FAILURES: dict[int, int] = {}


class PasswordIn(BaseModel):
    password: str = Field(min_length=8)


def _meta_get(ctx: AppContext, key: str):
    with ctx.db.connect() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return None if row is None else row["value"]


def _meta_set(ctx: AppContext, key: str, value: bytes) -> None:
    with ctx.db.connect() as conn:
        conn.execute(
            "INSERT INTO app_meta(key,value) VALUES(?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def _status(ctx: AppContext) -> dict:
    return {
        "initialized": _meta_get(ctx, "salt") is not None,
        "unlocked": ctx.vault.unlocked,
        "llm_mode": ctx.llm_service.mode(),
        "max_docs": ctx.settings.max_docs,
    }


@router.get("/status")
def status(ctx: AppContext = Depends(get_context)) -> dict:
    return _status(ctx)


@router.post("/setup")
def setup(payload: PasswordIn, ctx: AppContext = Depends(get_context)) -> dict:
    """首次初始化：同时写入 salt 与 canary，后续只需 canary 就能校验密码而无需存明文。"""
    if _meta_get(ctx, "salt") is not None:
        raise HTTPException(409, "系统已初始化，请直接解锁")
    salt = keys.new_salt()
    master = keys.derive_master_key(payload.password, salt)
    _meta_set(ctx, "salt", salt)
    _meta_set(ctx, "canary", keys.seal_canary(master))
    ctx.vault.set_master(master)
    ctx.types.load_from_repo(ctx.repo)
    ctx.repo.audit("session.setup", {})
    return _status(ctx)


@router.post("/unlock")
def unlock(
    payload: PasswordIn, request: Request, ctx: AppContext = Depends(get_context)
) -> dict:
    salt = _meta_get(ctx, "salt")
    canary = _meta_get(ctx, "canary")
    if salt is None or canary is None:
        raise HTTPException(400, "系统尚未初始化")
    master = keys.derive_master_key(payload.password, salt)
    if not keys.verify_canary(master, canary):
        # 前 4 次不延迟以免误输体验太差；第 5 次起指数退避，上限 4 秒；
        # 计数按 app 实例隔离，多实例时互不影响。
        app_key = id(request.app)
        count = _FAILURES.get(app_key, 0) + 1
        _FAILURES[app_key] = count
        if count >= 5:
            time.sleep(min(0.5 * (2 ** (count - 5)), 4))
        raise HTTPException(401, "主密码错误")
    # 成功后立即清零，避免之前的历史失败继续拖慢下一次输错
    _FAILURES.pop(id(request.app), None)
    ctx.vault.set_master(master)
    ctx.types.load_from_repo(ctx.repo)
    ctx.repo.audit("session.unlock", {})
    return _status(ctx)


@router.post("/lock")
def lock(ctx: AppContext = Depends(get_context)) -> dict:
    """清除内存中的主密钥；之后所有业务接口都会因未解锁而被拒绝。"""
    ctx.vault.lock()
    return _status(ctx)
