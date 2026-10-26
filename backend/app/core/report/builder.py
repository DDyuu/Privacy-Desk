from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.detect.rule_engine import Span
from app.core.mask.verifier import VerifyResult

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
_STYLE = ParagraphStyle("cn", fontName="STSong-Light", fontSize=10.5, leading=17)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_json_report(
    document: str,
    mode: str,
    detections: list[Span],
    applied: list[dict],
    verify: VerifyResult | None,
    stats: dict,
) -> dict:
    by_type: dict[str, int] = {}
    for span in detections:
        by_type[span.type_code] = by_type.get(span.type_code, 0) + 1
    return {
        "document": document,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "detected": len(detections),
            "by_type": by_type,
            "applied": len(applied),
            "residual": len(verify.residuals) if verify else None,
            "passed": verify.passed if verify else None,
        },
        "stats": stats,
        "metrics": verify.metrics if verify else {},
        "issues": verify.issues if verify else [],
        "detections": [span.to_dict() for span in detections],
        "applied": applied,
        "residuals": [span.to_dict() for span in verify.residuals] if verify else [],
    }


def build_pdf_report(report: dict) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title="脱敏报告")
    story = [Paragraph("文本隐私信息脱敏报告", ParagraphStyle(
        "title", parent=_STYLE, fontSize=18, leading=24, spaceAfter=12
    ))]
    summary = report["summary"]
    story.append(Paragraph(f"文件：{_escape(report['document'])}", _STYLE))
    story.append(Paragraph(f"识别模式：{_escape(report['mode'])}", _STYLE))
    story.append(Paragraph(f"生成时间：{_escape(report['generated_at'])}", _STYLE))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"识别隐私信息 {summary['detected']} 处，脱敏 {summary['applied']} 处", _STYLE))
    passed = summary["passed"]
    if passed is None:
        result_text = "未校验"
    elif passed:
        result_text = "通过"
    else:
        result_text = "未通过"
    story.append(Paragraph(f"校验结果：{result_text}", _STYLE))
    story.append(Spacer(1, 10))

    rows = [["隐私类型", "数量"]]
    for code, count in sorted(summary["by_type"].items()):
        rows.append([code, str(count)])
    table = Table(rows, colWidths=[280, 80])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C4D6")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    if report["issues"]:
        story.append(Paragraph("校验问题", ParagraphStyle("h", parent=_STYLE, fontSize=12)))
        for issue in report["issues"]:
            story.append(Paragraph(f"· {_escape(issue)}", _STYLE))
        story.append(Spacer(1, 8))

    story.append(Paragraph("脱敏明细", ParagraphStyle("h2", parent=_STYLE, fontSize=12)))
    detail_rows = [["起始", "结束", "类型", "方式", "替换结果"]]
    for item in report["applied"]:
        replacement = item["replacement"]
        if len(replacement) > 40:
            replacement = replacement[:40] + "…"
        detail_rows.append([
            str(item["start"]),
            str(item["end"]),
            item["type_code"],
            item["action"],
            replacement,
        ])
    detail = Table(detail_rows, colWidths=[50, 50, 120, 60, 160])
    detail.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C4D6")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(detail)
    document.build(story)
    return buffer.getvalue()
