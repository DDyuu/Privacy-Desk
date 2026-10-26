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
        host="127.0.0.1",
        port=int(os.environ.get("PRIVACY_DESK_PORT", "8765")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
