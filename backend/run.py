"""后端启动入口：先兜底标准流，再在本机回环地址上起服务，供桌面壳内嵌调用。"""

import os
import sys

# PyInstaller windowed (console=False) 运行时 sys.stdout/stderr 可能为 None，
# 而 uvicorn 的日志初始化需要可写的流；没有控制台时退化为 devnull。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import uvicorn

from app.config import Settings
from app.main import create_app


def main() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        # 只绑定回环地址，避免桌面端把包含隐私数据的接口暴露到局域网
        host="127.0.0.1",
        port=int(os.environ.get("PRIVACY_DESK_PORT", "8765")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
