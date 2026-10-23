import { Card, Empty, List, Tag, Tooltip, Typography } from "antd";
import type { DocumentMeta } from "../types";
import StatusTag from "./StatusTag";

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
  return (
    <Card size="small" title="文档列表" extra={<span className="list-count">{documents.length}</span>}>
      <div className="doc-list">
        <List
          loading={loading}
          dataSource={documents}
          split={false}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" /> }}
          renderItem={(doc) => (
            <div
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
          )}
        />
      </div>
    </Card>
  );
}
