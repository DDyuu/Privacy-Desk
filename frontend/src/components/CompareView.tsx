// 脱敏对比：左侧原文按敏感等级高亮，右侧脱敏文本对替换位置着色。
import type { ReactNode } from "react";
import { Alert, Card, Popover } from "antd";
import type { AppliedItem, Span, TypeDefinition } from "../types";

interface CompareViewProps {
  original: string;
  masked: string;
  spans: Span[];
  applied: AppliedItem[];
  byCode: Record<string, TypeDefinition>;
  /** 嵌入工作台主体时不再套一层 Card */
  embedded?: boolean;
}

function spanDetail(span: Span, byCode: Record<string, TypeDefinition>): ReactNode {
  return (
    <div className="popover-detail">
      <div>类型：{byCode[span.type_code]?.name ?? span.type_code}</div>
      <div>置信度：{Math.round(span.confidence * 100)}%</div>
      <div>来源：{span.source === "rule" ? "规则" : "大模型"}</div>
    </div>
  );
}

function codePointLength(value: string): number {
  return Array.from(value).length;
}

/** 后端返回的是 Python 码点偏移，前端字符串索引是 UTF-16，需要换算。 */
function toU16(text: string, codePointIndex: number): number {
  return Array.from(text).slice(0, Math.max(0, codePointIndex)).join("").length;
}

function renderOriginal(
  text: string,
  spans: Span[],
  byCode: Record<string, TypeDefinition>,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  // 先按起点排序，才能用一个游标顺序推进；后端返回的 span 顺序不保证有序
  const ordered = [...spans].sort((a, b) => a.start - b.start);
  const totalCodePoints = codePointLength(text);
  let cursor = 0;

  for (const span of ordered) {
    // 跳过空区间、越界以及与前一个片段重叠的 span，避免重复切片
    if (span.start >= span.end || span.end > totalCodePoints) continue;
    const start = toU16(text, span.start);
    const end = toU16(text, span.end);
    if (start < cursor || start >= end) continue;
    if (start > cursor) nodes.push(text.slice(cursor, start));
    nodes.push(
      <Popover
        key={`orig-${span.start}-${span.end}-${span.type_code}`}
        trigger={["hover", "click"]}
        content={spanDetail(span, byCode)}
      >
        <mark className={`hit-${span.level}`}>{text.slice(start, end)}</mark>
      </Popover>,
    );
    cursor = end;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function renderMasked(masked: string, applied: AppliedItem[]): ReactNode[] {
  const nodes: ReactNode[] = [];
  // 按起点排序后单游标推进
  const ordered = [...applied].sort((a, b) => a.start - b.start);
  let cursor = 0;
  // 替换会改变文本长度，delta 累积长度差，把原文坐标换算到脱敏文本坐标
  let delta = 0;

  for (const item of ordered) {
    const replacementLength = codePointLength(item.replacement);
    const startCodePoint = item.start + delta;
    const endCodePoint = startCodePoint + replacementLength;
    delta += replacementLength - (item.end - item.start);
    const start = toU16(masked, startCodePoint);
    const end = toU16(masked, endCodePoint);
    if (start < cursor || start >= end || end > masked.length) continue;
    if (start > cursor) nodes.push(masked.slice(cursor, start));
    nodes.push(
      <mark
        key={`mask-${item.start}-${item.end}-${item.type_code}`}
        className="mask-replacement"
      >
        {masked.slice(start, end)}
      </mark>,
    );
    cursor = end;
  }
  if (cursor < masked.length) nodes.push(masked.slice(cursor));
  return nodes;
}

export default function CompareView({
  original,
  masked,
  spans,
  applied,
  byCode,
  embedded = false,
}: CompareViewProps) {
  // 文本都以 React 文本节点渲染，天然转义 HTML，因此不需要手动处理 & < > 等字符
  const body = (
    <>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="颜色对应敏感等级；脱敏文本由后端生成"
      />
      <div className="compare-grid">
        <div>
          <div className="compare-title">原文</div>
          <div className="compare-pane mono">{renderOriginal(original, spans, byCode)}</div>
        </div>
        <div>
          <div className="compare-title">脱敏后</div>
          <div className="compare-pane mono">{renderMasked(masked, applied)}</div>
        </div>
      </div>
    </>
  );

  if (embedded) return <div className="compare-embedded">{body}</div>;
  return (
    <Card size="small" title="脱敏对比">
      {body}
    </Card>
  );
}
