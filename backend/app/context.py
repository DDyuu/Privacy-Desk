from dataclasses import dataclass

from app.config import Settings
from app.core.detect.types import TypeRegistry, load_builtin_types
from app.core.security.vault import Vault
from app.core.store.db import Database
from app.core.store.repository import Repository
from app.llm.service import LLMService


@dataclass
class AppContext:
    settings: Settings
    db: Database
    vault: Vault
    repo: Repository
    types: TypeRegistry
    llm_service: LLMService


def build_context(settings: Settings) -> AppContext:
    db = Database(settings.db_path)
    db.init()
    vault = Vault()
    repo = Repository(db, vault)
    registry = TypeRegistry(load_builtin_types(settings.resources_dir))
    return AppContext(
        settings=settings,
        db=db,
        vault=vault,
        repo=repo,
        types=registry,
        llm_service=LLMService(repo, settings),
    )
