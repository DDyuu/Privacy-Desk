import pytest

from app.config import Settings
from app.main import create_app


def test_enforce_integrity_without_manifest_fails(tmp_path):
    with pytest.raises(RuntimeError, match="完整性清单"):
        create_app(Settings(data_dir=tmp_path / "data", enforce_integrity=True))


def test_require_token_without_token_fails(tmp_path):
    with pytest.raises(RuntimeError, match="APP_TOKEN"):
        create_app(Settings(data_dir=tmp_path / "data", require_token=True))
