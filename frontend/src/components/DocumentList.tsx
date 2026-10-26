import { useEffect, useMemo, useState } from "react";
import { Card, Empty, Pagination, Spin, Tag, Tooltip, Typography } from "antd";
import type { DocumentMeta } from "../types";
import StatusTag from "./StatusTag";

/** 文档列表固定每页 3 条，列表区域高度保持不变 */
const PAGE_SIZE = 3;

interface DocumentListProps {
  documents: DocumentMeta[];
  selectedId: string | null;
  loading?: boolean;
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
  onSelect,
}: DocumentListProps) {
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [documents.length]);

  const visible = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return documents.slice(start, start + PAGE_SIZE);
  }, [documents, page]);

  return (
    <Card
      size="small"
      className="doc-list-card"
      title="文档列表"
      extra={<span className="list-count">{documents.length}</span>}
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
