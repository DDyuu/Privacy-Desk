"""应用级依赖容器：启动时一次性装配数据库、保险库、仓储、类型注册表与 LLM 服务。"""

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
    """唯一的装配入口；所有路由共享同一份实例，解锁状态也保存在 vault 中。"""
    db = Database(settings.db_path)
    # 先建表再构造仓储，保证首次启动时后续查询不会因缺表失败
    db.init()
    vault = Vault()
    repo = Repository(db, vault)
    # 内置类型来自（加密）资源包；用户自定义类型要等主密码解锁后再从库中加载
    registry = TypeRegistry(load_builtin_types(settings.resources_dir))
    return AppContext(
        settings=settings,
        db=db,
        vault=vault,
        repo=repo,
        types=registry,
        llm_service=LLMService(repo, settings),
    )
