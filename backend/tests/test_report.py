from io import BytesIO

import pdfplumber

from app.core.detect.rule_engine import Span
from app.core.mask.verifier import VerifyResult
from app.core.report.builder import build_json_report, build_pdf_report


def sample():
    span = Span(4, 15, "PHONE_CN", "13800138000", 0.99, "rule", "high")
    verify = VerifyResult(
        passed=True,
        residuals=[],
        metrics={"ratio": 1.0, "placeholder_density": 0.1, "residual_count": 0},
        issues=[],
    )
    applied = [
        {
            "start": 4,
            "end": 15,
            "type_code": "PHONE_CN",
            "action": "mask",
            "replacement": "*******8000",
        }
    ]
    return build_json_report(
        "样例.txt", "rules", [span], applied, verify, {"detected": 1, "applied": 1}
    )


def test_json_report_contains_summary_and_detections():
    report = sample()
    assert report["document"] == "样例.txt"
    assert report["summary"]["detected"] == 1
    assert report["summary"]["by_type"]["PHONE_CN"] == 1
    assert report["summary"]["passed"] is True
    assert report["detections"][0]["type_code"] == "PHONE_CN"


def test_json_report_includes_llm_calls():
    report = build_json_report(
        "样例.txt",
        "online",
        [],
        [],
        None,
        {},
        llm={
            "mode": "online",
            "calls": [
                {
                    "index": 0,
                    "raw": '[{"type":"NAME_CN"}]',
                    "items": 1,
                    "cached": False,
                    "elapsed_ms": 12,
                }
            ],
            "truncated": False,
        },
    )
    assert report["llm"]["mode"] == "online"
    assert report["llm"]["calls"][0]["raw"] == '[{"type":"NAME_CN"}]'
    assert report["llm"]["truncated"] is False


def test_json_report_defaults_to_empty_llm_calls():
    report = sample()
    assert report["llm"]["calls"] == []
    assert report["llm"]["truncated"] is False


def test_pdf_report_is_valid_pdf():
    payload = build_pdf_report(sample())
    assert payload.startswith(b"%PDF")
    assert len(payload) > 800


def test_pdf_report_escapes_special_document_name():
    report = sample()
    report["document"] = "A&B <机密>.txt"
    payload = build_pdf_report(report)
    assert payload.startswith(b"%PDF")


def test_pdf_report_marks_unverified():
    report = sample()
    report["summary"]["passed"] = None
    payload = build_pdf_report(report)
    with pdfplumber.open(BytesIO(payload)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "未校验" in text


def test_pdf_report_renders_llm_calls():
    report = sample()
    report["llm"] = {
        "mode": "online",
        "calls": [
            {"index": 0, "chars": 12, "items": 1, "elapsed_ms": 30, "cached": False}
        ],
        "truncated": False,
    }
    payload = build_pdf_report(report)
    assert payload.startswith(b"%PDF")
    with pdfplumber.open(BytesIO(payload)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "模型调用" in text
