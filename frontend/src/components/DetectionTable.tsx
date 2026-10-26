import { useMemo, useState } from "react";
import { Empty, Select, Space, Spin, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Level, Span, TypeDefinition } from "../types";

const LEVEL_META: Record<Level, { label: string; color: string }> = {
  high: { label: "高", color: "red" },
  medium: { label: "中", color: "orange" },
  low: { label: "低", color: "blue" },
};

interface DetectionTableProps {
  spans: Span[];
  byCode: Record<string, TypeDefinition>;
  loading?: boolean;
}

export default function DetectionTable({ spans, byCode, loading = false }: DetectionTableProps) {
  const [filterCode, setFilterCode] = useState("all");

  const codes = useMemo(
    () => Array.from(new Set(spans.map((span) => span.type_code))),
    [spans],
  );

  const activeFilter = filterCode === "all" || codes.includes(filterCode) ? filterCode : "all";

  const rows = useMemo(() => {
    const filtered =
      activeFilter === "all" ? spans : spans.filter((span) => span.type_code === activeFilter);
    return [...filtered].sort((a, b) => a.start - b.start);
  }, [spans, activeFilter]);

  const columns: ColumnsType<Span> = [
    {
      title: "类型",
      dataIndex: "type_code",
      width: 104,
      render: (code: string) => {
        const name = byCode[code]?.name ?? code;
        return (
          <Tooltip title={name === code ? code : `${name}（${code}）`}>
            <span className="ellipsis">{name}</span>
          </Tooltip>
        );
      },
    },
    {
      title: "片段",
      dataIndex: "text",
      width: 140,
      render: (text: string) => (
        <Tooltip title={text}>
          <span className="mono ellipsis">{text.length > 14 ? `${text.slice(0, 14)}…` : text}</span>
        </Tooltip>
      ),
    },
    {
      title: "位置",
      width: 96,
      render: (_, span) => (
        <span className="mono text-muted">
          {span.start}-{span.end}
        </span>
      ),
    },
    {
      title: "置信度",
      width: 70,
      render: (_, span) => `${Math.round(span.confidence * 100)}%`,
    },
    {
      title: "来源",
      dataIndex: "source",
      width: 64,
      render: (source: Span["source"]) => (
        <Tag color={source === "rule" ? "geekblue" : "purple"}>{source === "rule" ? "规则" : "LLM"}</Tag>
      ),
    },
    {
      title: "等级",
      dataIndex: "level",
      width: 58,
      render: (level: Level) => <Tag color={LEVEL_META[level].color}>{LEVEL_META[level].label}</Tag>,
    },
  ];

  return (
    <div className="detection-table">
      {spans.length === 0 ? (
        <div className="detection-empty">
          {loading ? (
            <Spin />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先执行识别" />
          )}
        </div>
      ) : (
        <>
          <Space wrap style={{ marginBottom: 10 }}>
            <Select
              size="small"
              style={{ width: 168 }}
              value={activeFilter}
              onChange={setFilterCode}
              options={[
                { value: "all", label: "全部类型" },
                ...codes.map((code) => ({ value: code, label: byCode[code]?.name ?? code })),
              ]}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              共 {rows.length} 处
            </Typography.Text>
          </Space>
          <Table<Span>
            size="small"
            rowKey={(span) => `${span.start}-${span.end}-${span.type_code}`}
            loading={loading}
            columns={columns}
            dataSource={rows}
            pagination={{ pageSize: 8, size: "small", showSizeChanger: false, hideOnSinglePage: true }}
            scroll={{ x: 532 }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={loading ? "正在识别…" : "请先执行识别"}
                />
              ),
            }}
          />
        </>
      )}
    </div>
  );
}
