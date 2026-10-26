from app.core.security import keys


def test_derive_is_deterministic_and_different_for_wrong_password():
    salt = keys.new_salt()
    right = keys.derive_master_key("password123", salt)
    again = keys.derive_master_key("password123", salt)
    wrong = keys.derive_master_key("password456", salt)
    assert right == again
    assert right != wrong
    assert len(right) == 32


def test_data_key_differs_from_master_key():
    salt = keys.new_salt()
    master = keys.derive_master_key("password123", salt)
    assert keys.derive_data_key(master) != master
    assert len(keys.derive_data_key(master)) == 32


def test_canary_verifies_only_with_correct_key():
    salt = keys.new_salt()
    master = keys.derive_master_key("password123", salt)
    sealed = keys.seal_canary(master)
    assert keys.verify_canary(master, sealed) is True
    other = keys.derive_master_key("password456", salt)
    assert keys.verify_canary(other, sealed) is False
