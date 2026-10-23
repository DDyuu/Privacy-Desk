from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Detector(BaseModel):
    kind: Literal["regex", "checksum", "keyword", "dict", "llm"]
    pattern: str | None = None
    flags: list[str] = Field(default_factory=list)
    algo: str | None = None
    words: list[str] = Field(default_factory=list)
    hint: str | None = None


class TypeDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    name: str
    category: str
    level: Literal["high", "medium", "low"] = "medium"
    builtin: bool = False
    enabled: bool = True
    detectors: list[Detector]
    default_action: Literal["mask", "replace", "fuzz", "encrypt"] = Field("mask", alias="defaultAction")
    action_options: dict[str, Any] = Field(default_factory=dict, alias="actionOptions")


class TypeRegistry:
    """内置类型与用户自定义类型的合并视图。"""

    def __init__(self, types: list[TypeDefinition]) -> None:
        self._types: dict[str, TypeDefinition] = {item.code: item for item in types}

    def list(self) -> list[TypeDefinition]:
        return [item for item in self._types.values() if item.enabled]

    def all(self) -> list[TypeDefinition]:
        return list(self._types.values())

    def get(self, code: str) -> TypeDefinition:
        if code not in self._types:
            raise KeyError(f"未知隐私类型：{code}")
        return self._types[code]

    def upsert(self, definition: TypeDefinition) -> None:
        self._types[definition.code] = definition

    def remove(self, code: str) -> None:
        self._types.pop(code, None)

    def load_from_repo(self, repo) -> None:
        """解锁后把自定义类型合并进注册表；未解锁时静默跳过。"""
        try:
            payloads = repo.list_types()
        except Exception:
            return
        for payload in payloads:
            self.upsert(TypeDefinition.model_validate(payload))


def load_builtin_types(resources_dir: Path) -> list[TypeDefinition]:
    from app.core.security.resources import load_bundle

    payload = load_bundle(resources_dir)["types"]
    return [TypeDefinition.model_validate(item) for item in payload]
