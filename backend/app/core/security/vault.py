from app.core.security import keys


class LockedError(RuntimeError):
    """未解锁时访问密钥。"""


class Vault:
    """主密钥仅保存在内存，锁定时丢弃引用。"""

    def __init__(self) -> None:
        self._master: bytes | None = None

    @property
    def unlocked(self) -> bool:
        return self._master is not None

    def set_master(self, master_key: bytes) -> None:
        self._master = master_key

    def lock(self) -> None:
        self._master = None

    def master_key(self) -> bytes:
        if self._master is None:
            raise LockedError("请先输入主密码解锁")
        return self._master

    def data_key(self) -> bytes:
        return keys.derive_data_key(self.master_key())
