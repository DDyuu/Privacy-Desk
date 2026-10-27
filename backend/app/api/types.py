"""自定义识别类型接口：列表、正则生成、保存/删除与样本试跑。"""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_context, require_unlocked
from app.context import AppContext
from app.core.detect.regex_synth import synthesize_pattern
from app.core.detect.rule_engine import RuleEngine
from app.core.detect.types import TypeDefinition

router = APIRouter(prefix="/types", tags=["types"])


class TypeTestIn(BaseModel):
    type: TypeDefinition
    samples: list[str]


class GeneratePatternIn(BaseModel):
    samples: list[str] = []


@router.get("")
def list_types(ctx: AppContext = Depends(get_context)) -> list[dict]:
    require_unlocked(ctx)
    return [item.model_dump(by_alias=True) for item in ctx.types.all()]


@router.post("/generate-pattern")
def generate_pattern(
    payload: GeneratePatternIn, ctx: AppContext = Depends(get_context)
) -> dict:
    """根据正例归纳一个候选正则，不调用大模型。"""
    require_unlocked(ctx)
    return synthesize_pattern(payload.samples)


@router.put("/{code}")
def save_type(
    code: str, payload: TypeDefinition, ctx: AppContext = Depends(get_context)
) -> dict:
    require_unlocked(ctx)
    if payload.code != code:
        raise HTTPException(400, "路径中的类型代码与请求体不一致")
    try:
        existing = ctx.types.get(code)
    except KeyError:
        existing = None
    if existing is not None and existing.builtin:
        raise HTTPException(403, "内置类型不可覆盖")
    if not payload.detectors:
        raise HTTPException(400, "至少需要一个识别器")
    # 正则先预编译再落库：非法表达式在这里就挡下，
    # 否则保存成功后每次识别都会在运行期抛 re.error。
    for detector in payload.detectors:
        if detector.kind == "regex":
            try:
                re.compile(detector.pattern or "")
            except re.error as exc:
                raise HTTPException(400, f"正则表达式无效：{exc}") from exc
    ctx.types.upsert(payload)
    ctx.repo.save_type(code, payload.model_dump(by_alias=True))
    ctx.repo.audit("type.save", {"code": code})
    return payload.model_dump(by_alias=True)


@router.delete("/{code}")
def delete_type(code: str, ctx: AppContext = Depends(get_context)) -> dict:
    require_unlocked(ctx)
    try:
        definition = ctx.types.get(code)
    except KeyError as exc:
        raise HTTPException(404, "类型不存在") from exc
    if definition.builtin:
        raise HTTPException(403, "内置类型不可删除")
    ctx.types.remove(code)
    ctx.repo.delete_type(code)
    ctx.repo.audit("type.delete", {"code": code})
    return {"deleted": code}


@router.post("/test")
def test_type(payload: TypeTestIn, ctx: AppContext = Depends(get_context)) -> dict:
    """只用规则引擎试跑样本，不触发大模型调用，便于快速校验正则与关键词。"""
    require_unlocked(ctx)
    engine = RuleEngine([payload.type])
    try:
        results = [
            {"sample": sample, "spans": [span.to_dict() for span in engine.detect(sample)]}
            for sample in payload.samples
        ]
    except re.error as exc:
        raise HTTPException(400, f"正则表达式无效：{exc}") from exc
    return {"results": results}
