# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：只打入口与加密资源，明文资源（types.default.json、prompts）不打入。"""

import os
from pathlib import Path

# PyInstaller 打包时 cwd 不一定是 build/，因此优先用 SPECPATH 定位本文件所在目录
_SPEC_DIR = Path(globals().get("SPECPATH", os.getcwd())).resolve()
_BACKEND_DIR = _SPEC_DIR.parent if _SPEC_DIR.name == "build" else _SPEC_DIR

a = Analysis(
    [str(_BACKEND_DIR / "run.py")],
    pathex=[str(_BACKEND_DIR)],
    binaries=[],
    # 只打包加密后的资源包；明文的 types.default.json 与 prompts 故意不进入分发
    datas=[(str(_BACKEND_DIR / "resources" / "rules.enc"), "resources")],
    # uvicorn 的实现模块是运行时按配置动态导入的，静态分析看不到，必须显式声明
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="privacy-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 桌面端不弹控制台窗口，所以 run.py 需要为 stdout/stderr 为 None 的情况兜底
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    # one-dir 布局：构建后脚本才能向 _internal 追加加密资源与完整性清单
    strip=False,
    upx=False,
    upx_exclude=[],
    name="privacy-backend",
)
