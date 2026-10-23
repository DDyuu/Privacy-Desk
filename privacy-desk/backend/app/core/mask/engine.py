from __future__ import annotations

from dataclasses import dataclass

from app.core.detect.rule_engine import Span
from app.core.detect.types import TypeRegistry
from app.core.mask.operators import encrypt_value, fuzz_value, mask_value

VALID_ACTIONS = {"mask", "replace", "fuzz", "encrypt"}


@dataclass
class MaskResult:
    masked_text: str
    applied: list[dict]
    mapping_size: int


def default_actions(registry: TypeRegistry) -> dict[str, dict]:
    return {
        definition.code: {
            "action": definition.default_action,
            "options": dict(definition.action_options),
        }
        for definition in registry.all()
    }


class MaskEngine:
    def __init__(
        self,
        data_key: bytes,
        registry: TypeRegistry,
        actions: dict[str, dict] | None = None,
    ) -> None:
        self._key = data_key
        self._registry = registry
        merged = default_actions(registry)
        for code, spec in (actions or {}).items():
            if not isinstance(spec, dict):
                raise ValueError("脱敏配置格式非法")
            options = spec.get("options") or {}
            if not isinstance(options, dict):
                raise ValueError("脱敏选项格式非法")
            base = merged.get(code, {"action": "mask", "options": {}})
            action = spec.get("action", base.get("action", "mask"))
            if action not in VALID_ACTIONS:
                raise ValueError(f"未知脱敏方式：{action}")
            merged[code] = {
                "action": action,
                "options": {**(base.get("options") or {}), **(spec.get("options") or {})},
            }
        self._actions = merged

    def apply(self, text: str, spans: list[Span], aad_prefix: str = "doc") -> MaskResult:
        ordered = sorted(spans, key=lambda item: item.start)
        for previous, current in zip(ordered, ordered[1:]):
            if current.start < previous.end:
                raise ValueError("识别结果存在重叠，无法脱敏")
        for span in ordered:
            if not (0 <= span.start <= span.end <= len(text)) or text[span.start:span.end] != span.text:
                raise ValueError("识别结果与原文不一致，无法脱敏")
        counters: dict[str, int] = {}
        mapping: dict[tuple[str, str], str] = {}
        replacements: list[tuple[Span, str, str]] = []
        for span in ordered:
            spec = self._actions.get(span.type_code, {"action": "mask", "options": {}})
            action = spec.get("action", "mask")
            options = spec.get("options") or {}
            if action == "replace":
                key = (span.type_code, span.text)
                if key not in mapping:
                    count = counters.get(span.type_code, 0) + 1
                    counters[span.type_code] = count
                    label = self._registry.get(span.type_code).name
                    mapping[key] = f"[{label}_{count}]"
                replacement = mapping[key]
            elif action == "fuzz":
                replacement = fuzz_value(span.text, span.type_code)
            elif action == "encrypt":
                aad = f"{aad_prefix}:{span.type_code}:{span.start}".encode("utf-8")
                replacement = encrypt_value(span.text, self._key, aad)
            else:
                replacement = mask_value(
                    span.text,
                    keep_prefix=int(options.get("keepPrefix", 0)),
                    keep_suffix=int(options.get("keepSuffix", 0)),
                )
            replacements.append((span, action, replacement))
        masked = text
        for span, _, replacement in sorted(replacements, key=lambda item: -item[0].start):
            masked = masked[: span.start] + replacement + masked[span.end:]
        applied = [
            {
                "start": span.start,
                "end": span.end,
                "type_code": span.type_code,
                "action": action,
                "replacement": replacement,
            }
            for span, action, replacement in replacements
        ]
        return MaskResult(masked_text=masked, applied=applied, mapping_size=len(mapping))
