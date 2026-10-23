from fastapi import HTTPException, Request

from app.context import AppContext
from app.core.security import keys


def get_context(request: Request) -> AppContext:
    return request.app.state.ctx


def require_unlocked(ctx: AppContext) -> None:
    if not ctx.vault.unlocked:
        raise HTTPException(401, "请先输入主密码解锁")


def verify_password(ctx: AppContext, password: str | None) -> None:
    """导出敏感报告前再次校验主密码。"""
    if not password:
        raise HTTPException(401, "导出报告需要再次输入主密码")
    with ctx.db.connect() as conn:
        salt = conn.execute("SELECT value FROM app_meta WHERE key='salt'").fetchone()
        canary = conn.execute("SELECT value FROM app_meta WHERE key='canary'").fetchone()
    if salt is None or canary is None:
        raise HTTPException(400, "系统尚未初始化")
    master = keys.derive_master_key(password, salt["value"])
    if not keys.verify_canary(master, canary["value"]):
        raise HTTPException(403, "主密码错误")
