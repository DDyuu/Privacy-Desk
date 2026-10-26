import pytest

from app.core.security.vault import LockedError, Vault


def test_vault_requires_unlock():
    vault = Vault()
    assert vault.unlocked is False
    with pytest.raises(LockedError):
        vault.data_key()


def test_lock_clears_key():
    vault = Vault()
    vault.set_master(b"m" * 32)
    assert len(vault.data_key()) == 32
    vault.lock()
    assert vault.unlocked is False
    with pytest.raises(LockedError):
        vault.master_key()
