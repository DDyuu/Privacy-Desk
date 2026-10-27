"""FastAPI 应用装配：启动期自检、令牌中间件、路由注册与前端静态资源挂载。"""

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import batches, documents, session, types
from app.api import settings as settings_api
from app.config import Settings
from app.context import build_context
from app.core.security.integrity import verify_manifest


def _check_startup_settings(settings: Settings) -> None:
    """启动期一次性校验加固开关；任一条件不满足就拒绝启动，避免带病运行。"""
    if settings.require_token and not settings.app_token:
        raise RuntimeError("缺少 APP_TOKEN，拒绝启动")
    if settings.require_encrypted_resources:
        # 资源解密器读取的是环境变量而非 Settings，这里同步开关，
        # 使本进程内后续的资源加载也只能走加密包。
        os.environ["PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES"] = "1"
    if not settings.enforce_integrity:
        return
    # 加密资源与清单由构建脚本放在同一运行时根目录（resources 的上一级），
    # 校验范围覆盖该目录下所有被打包的文件。
    manifest_path = Path(
        os.environ.get("PRIVACY_DESK_MANIFEST", str(settings.resources_dir.parent / "manifest.json"))
    )
    if not manifest_path.exists():
        raise RuntimeError("缺少完整性清单 manifest.json")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = payload["manifest"]
        signature = payload["signature"]
        if not isinstance(manifest, dict) or not isinstance(signature, str):
            raise ValueError("manifest 或 signature 类型非法")
        problems = verify_manifest(settings.resources_dir.parent, manifest, signature)
    except Exception as exc:
        raise RuntimeError(f"完整性清单格式非法：{exc}") from exc
    if problems:
        raise RuntimeError("完整性校验失败：" + "; ".join(problems[:5]))


def create_app(settings: Settings | None = None) -> FastAPI:
    """装配并返回应用实例；测试可注入自定义 Settings。"""
    settings = settings or Settings()
    _check_startup_settings(settings)
    ctx = build_context(settings)
    app = FastAPI(title="Privacy Desk", version="0.1.0")
    app.state.ctx = ctx
    app.state.settings = settings

    # 桌面端前端与接口同源，但开发模式下前端跑在独立端口；
    # 鉴权靠请求头令牌而非 Cookie，所以允许通配来源且不携带凭据。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def token_guard(request, call_next):
        """保护 /api/ 前缀：CORS 只约束浏览器行为，令牌头才是接口侧的鉴权校验。"""
        # CORS 预检请求不会携带自定义令牌头，放行交给 CORSMiddleware 处理
        if request.method == "OPTIONS":
            return await call_next(request)
        if settings.app_token and request.url.path.startswith("/api/"):
            if request.headers.get("X-App-Token") != settings.app_token:
                return JSONResponse({"detail": "启动令牌无效"}, status_code=401)
        return await call_next(request)

    app.include_router(session.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(types.router, prefix="/api/v1")
    app.include_router(settings_api.router, prefix="/api/v1")
    app.include_router(batches.router, prefix="/api/v1")

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok", "llm_mode": ctx.llm_service.mode()}

    # 前端产物在冻结布局中位于 _MEIPASS 的上一级 frontend/dist；
    # 挂在 "/" 必须放在所有路由之后，否则会先于 /api/ 命中静态文件。
    ui_dir = Path(
        settings.ui_dir
        or (settings.resources_dir.parent.parent / "frontend" / "dist")
    )
    if ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app
