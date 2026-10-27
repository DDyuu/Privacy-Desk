// 文档列表：固定每页 3 条展示历史文档，并提供切换与清空入口。
import { useEffect, useMemo, useState } from "react";
import { DeleteOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Empty,
  Pagination,
  Popconfirm,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { DocumentMeta } from "../types";
import StatusTag from "./StatusTag";

/** 文档列表固定每页 3 条，列表区域高度保持不变 */
const PAGE_SIZE = 3;

interface DocumentListProps {
  documents: DocumentMeta[];
  selectedId: string | null;
  loading?: boolean;
  maxDocs?: number;
  clearing?: boolean;
  onClear?: () => void;
  onSelect: (id: string) => void;
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function DocumentList({
  documents,
  selectedId,
  loading = false,
  maxDocs,
  clearing = false,
  onClear,
  onSelect,
}: DocumentListProps) {
  const [page, setPage] = useState(1);

  useEffect(() => {
    // 文档数量变化（新增/清空）后回到第 1 页，防止当前页码超出新的总页数
    setPage(1);
  }, [documents.length]);

  // 配合 CSS 中 .doc-item 固定 64px 行高，3 条一页让列表区域高度稳定，翻页时不抖动
  const visible = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return documents.slice(start, start + PAGE_SIZE);
  }, [documents, page]);

  return (
    <Card
      size="small"
      className="doc-list-card"
      title="文档列表"
      extra={
        <Space size={8}>
          {/* 展示“已存数量 / 后端容量上限”，maxDocs 为空时只显示数量 */}
          <span className="list-count">
            {documents.length}
            {maxDocs ? ` / ${maxDocs}` : ""}
          </span>
          {/* 清空会连同原文与结果一起删除，属不可恢复操作，先由 Popconfirm 二次确认 */}
          {documents.length > 0 && onClear ? (
            <Popconfirm
              title="清空全部文档？"
              description="原文、识别结果、脱敏结果和报告都会被删除，且无法恢复。"
              okText="清空"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={onClear}
            >
              <Button
                size="small"
                icon={<DeleteOutlined />}
                loading={clearing}
              >
                清空历史
              </Button>
            </Popconfirm>
          ) : null}
        </Space>
      }
    >
      <div className="doc-list">
        {documents.length === 0 ? (
          <div className="doc-empty">
            {loading ? (
              <Spin size="small" />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" />
            )}
          </div>
        ) : (
          visible.map((doc) => (
            <div
              key={doc.id}
              role="button"
              tabIndex={0}
              className={`doc-item${doc.id === selectedId ? " active" : ""}`}
              onClick={() => onSelect(doc.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(doc.id);
                }
              }}
            >
              <Tooltip title={doc.name}>
                <div className="doc-item-name">{doc.name}</div>
              </Tooltip>
              <div className="doc-item-meta">
                <Tag color="blue">{doc.ext}</Tag>
                <StatusTag status={doc.status} />
                <Typography.Text type="secondary" className="doc-item-time">
                  {formatTime(doc.updated_at)}
                </Typography.Text>
              </div>
            </div>
          ))
        )}
      </div>
      {documents.length > PAGE_SIZE ? (
        <Pagination
          className="doc-pagination"
          size="small"
          current={page}
          pageSize={PAGE_SIZE}
          total={documents.length}
          showSizeChanger={false}
          onChange={setPage}
        />
      ) : null}
    </Card>
  );
}
