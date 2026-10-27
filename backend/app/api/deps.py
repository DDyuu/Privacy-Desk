"""路由公共依赖：获取上下文、解锁检查，以及敏感操作前的主密码二次校验。"""

from fastapi import HTTPException, Request

from app.context import AppContext
from app.core.security import keys


def get_context(request: Request) -> AppContext:
    return request.app.state.ctx


def require_unlocked(ctx: AppContext) -> None:
    # 未解锁时内存里没有主密钥，任何读写文档的接口都不可用
    if not ctx.vault.unlocked:
        raise HTTPException(401, "请先输入主密码解锁")


def verify_password(ctx: AppContext, password: str | None, action: str = "导出报告") -> None:
    """执行敏感操作前再次校验主密码。"""
    if not password:
        raise HTTPException(401, f"{action}需要再次输入主密码")
    # 用库中的 salt 重新派生密钥并与 canary 比对，既不依赖当前解锁态，也不落库明文
    with ctx.db.connect() as conn:
        salt = conn.execute("SELECT value FROM app_meta WHERE key='salt'").fetchone()
        canary = conn.execute("SELECT value FROM app_meta WHERE key='canary'").fetchone()
    if salt is None or canary is None:
        raise HTTPException(400, "系统尚未初始化")
    master = keys.derive_master_key(password, salt["value"])
    if not keys.verify_canary(master, canary["value"]):
        raise HTTPException(403, "主密码错误")
