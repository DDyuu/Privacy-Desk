"""内存中的主密钥容器：只持有引用，不负责持久化与落盘。"""

from app.core.security import keys


class LockedError(RuntimeError):
    """未解锁时访问密钥。"""


class Vault:
    """主密钥仅保存在内存，锁定时丢弃引用。"""

    def __init__(self) -> None:
        # 主密钥只驻留内存：不写盘、不进日志、不进入序列化结构；进程退出即消失
        self._master: bytes | None = None

    @property
    def unlocked(self) -> bool:
        return self._master is not None

    def set_master(self, master_key: bytes) -> None:
        self._master = master_key

    def lock(self) -> None:
        # 置空引用即视为上锁；已派生并缓存在别处的数据密钥不受影响
        self._master = None

    def master_key(self) -> bytes:
        if self._master is None:
            raise LockedError("请先输入主密码解锁")
        return self._master

    def data_key(self) -> bytes:
        # 每次调用都重新派生，不缓存子密钥，避免锁定后仍残留可用的数据密钥
        return keys.derive_data_key(self.master_key())
