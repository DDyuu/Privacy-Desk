// 脱敏对比：左侧原文按敏感等级高亮，右侧脱敏文本对替换位置着色。
import { useState, type ReactNode } from "react";
import { Alert, Card } from "antd";
import type { AppliedItem, Span } from "../types";

// 原文与替换串共用的配对键：同一片段的左右两栏高亮靠它关联
const pairKey = (start: number, end: number, typeCode: string) =>
  `${start}-${end}-${typeCode}`;

interface CompareViewProps {
  original: string;
  masked: string;
  spans: Span[];
  applied: AppliedItem[];
  /** 嵌入工作台主体时不再套一层 Card */
  embedded?: boolean;
}

// 原文中这些字符之后允许换行；替换串长度不变时按相同位置插入 wbr
const BREAK_AFTER = new Set([" ", "-", "/", "\\", ":", "_", ".", ",", ";", "|", ")", "]", "}"]);

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
  activeKey: string | null,
  onHover: (key: string | null) => void,
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
    const key = pairKey(span.start, span.end, span.type_code);
    nodes.push(
      <mark
        key={`orig-${key}`}
        className={`hit-${span.level}${activeKey === key ? " link-active" : ""}`}
        onMouseEnter={() => onHover(key)}
        onMouseLeave={() => onHover(null)}
      >
        {text.slice(start, end)}
      </mark>,
    );
    cursor = end;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

/** 替换串与原片段等长时，按原文断点插入零宽换行机会，让两栏在同一位置折行。 */
function renderReplacement(
  replacement: string,
  item: AppliedItem,
  originalChars: string[],
): ReactNode {
  const chars = Array.from(replacement);
  const originalLength = item.end - item.start;
  // 长度不同（替换 / 模糊化 / 加密）无法一一对应，交给浏览器自然换行
  if (chars.length !== originalLength) return replacement;
  const nodes: ReactNode[] = [];
  let chunk = "";
  chars.forEach((char, index) => {
    chunk += char;
    const source = originalChars[item.start + index];
    if (source && BREAK_AFTER.has(source) && index < chars.length - 1) {
      nodes.push(chunk);
      nodes.push(<wbr key={`wbr-${item.start + index}`} />);
      chunk = "";
    }
  });
  if (chunk) nodes.push(chunk);
  return nodes;
}

function renderMasked(
  masked: string,
  applied: AppliedItem[],
  spans: Span[],
  original: string,
  activeKey: string | null,
  onHover: (key: string | null) => void,
): ReactNode[] {
  const originalChars = Array.from(original);
  const nodes: ReactNode[] = [];
  const appliedKeys = new Set(
    applied.map((item) => pairKey(item.start, item.end, item.type_code)),
  );
  // 已识别但未脱敏（如被忽略）的片段在密文里仍是明文，同样参与悬停联动
  const kept = spans.filter(
    (span) =>
      span.start < span.end && !appliedKeys.has(pairKey(span.start, span.end, span.type_code)),
  );
  type MaskEvent = { kind: "applied"; item: AppliedItem } | { kind: "kept"; span: Span };
  const events: MaskEvent[] = [
    ...applied.map((item) => ({ kind: "applied" as const, item })),
    ...kept.map((span) => ({ kind: "kept" as const, span })),
  ].sort((a, b) => {
    const aStart = a.kind === "applied" ? a.item.start : a.span.start;
    const bStart = b.kind === "applied" ? b.item.start : b.span.start;
    return aStart - bStart;
  });

  let cursor = 0;
  // 替换会改变文本长度，delta 累积长度差，把原文坐标换算到脱敏文本坐标
  let delta = 0;

  for (const event of events) {
    let startCodePoint: number;
    let endCodePoint: number;
    if (event.kind === "applied") {
      const replacementLength = codePointLength(event.item.replacement);
      startCodePoint = event.item.start + delta;
      endCodePoint = startCodePoint + replacementLength;
      delta += replacementLength - (event.item.end - event.item.start);
    } else {
      // 未脱敏片段长度不变，只受前面替换的累计偏移影响
      startCodePoint = event.span.start + delta;
      endCodePoint = event.span.end + delta;
    }

    const start = toU16(masked, startCodePoint);
    const end = toU16(masked, endCodePoint);
    if (start < cursor || start >= end || end > masked.length) continue;
    if (start > cursor) nodes.push(masked.slice(cursor, start));

    const key =
      event.kind === "applied"
        ? pairKey(event.item.start, event.item.end, event.item.type_code)
        : pairKey(event.span.start, event.span.end, event.span.type_code);
    if (event.kind === "applied") {
      nodes.push(
        <mark
          key={`mask-${key}`}
          className={`mask-replacement${activeKey === key ? " link-active" : ""}`}
          onMouseEnter={() => onHover(key)}
          onMouseLeave={() => onHover(null)}
        >
          {renderReplacement(masked.slice(start, end), event.item, originalChars)}
        </mark>,
      );
    } else {
      nodes.push(
        <mark
          key={`kept-${key}`}
          className={`mask-kept${activeKey === key ? " link-active" : ""}`}
          title="已识别但未脱敏"
          onMouseEnter={() => onHover(key)}
          onMouseLeave={() => onHover(null)}
        >
          {masked.slice(start, end)}
        </mark>,
      );
    }
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
  embedded = false,
}: CompareViewProps) {
  // 文本都以 React 文本节点渲染，天然转义 HTML，因此不需要手动处理 & < > 等字符
  // 左右两栏共享同一个高亮键：悬停任意一侧，对应的另一侧同步高亮
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const body = (
    <>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="蓝色标记为敏感片段；悬停任意一侧，两侧对应内容会同时变红"
      />
      <div className="compare-grid">
        <div className="compare-col">
          <div className="compare-title">原文</div>
          <div className="compare-pane mono">
            {renderOriginal(original, spans, activeKey, setActiveKey)}
          </div>
        </div>
        <div className="compare-col">
          <div className="compare-title">脱敏后</div>
          <div className="compare-pane mono">
            {renderMasked(masked, applied, spans, original, activeKey, setActiveKey)}
          </div>
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
