# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：只打入口与加密资源，明文资源（types.default.json、prompts）不打入。"""

import os
from pathlib import Path

_SPEC_DIR = Path(globals().get("SPECPATH", os.getcwd())).resolve()
_BACKEND_DIR = _SPEC_DIR.parent if _SPEC_DIR.name == "build" else _SPEC_DIR

a = Analysis(
    [str(_BACKEND_DIR / "run.py")],
    pathex=[str(_BACKEND_DIR)],
    binaries=[],
    datas=[(str(_BACKEND_DIR / "resources" / "rules.enc"), "resources")],
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
    strip=False,
    upx=False,
    upx_exclude=[],
    name="privacy-backend",
)
