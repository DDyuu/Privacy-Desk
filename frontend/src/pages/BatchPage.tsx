import { useCallback, useEffect, useRef, useState } from "react";
import { InboxOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  List,
  Progress,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { api, errorText } from "../api/client";
import type { BatchStatus } from "../types";

/** 与后端 ALLOWED_EXTS 保持一致 */
const ACCEPT = ".txt,.md,.log,.py,.java,.js,.ts,.json,.csv,.eml,.docx,.pdf,.doc";
const POLL_INTERVAL = 1500;

type BatchItem = BatchStatus["items"][number];

const ITEM_STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: "等待中", color: "default" },
  running: { label: "处理中", color: "processing" },
  done: { label: "已完成", color: "success" },
  failed: { label: "失败", color: "error" },
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

interface BatchPageProps {
  onOpenDoc: (docId: string) => void;
}

export default function BatchPage({ onOpenDoc }: BatchPageProps) {
  const { message } = App.useApp();
  const [files, setFiles] = useState<File[]>([]);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchStatus | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const finishedRef = useRef<string | null>(null);

  const addFiles = useCallback((incoming: File[]) => {
    setFiles((prev) => {
      const seen = new Set(prev.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
      const next = [...prev];
      for (const file of incoming) {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (!seen.has(key)) {
          seen.add(key);
          next.push(file);
        }
      }
      return next;
    });
  }, []);

  const handleStart = async () => {
    if (files.length === 0) return;
    setCreating(true);
    setError("");
    setBatch(null);
    finishedRef.current = null;
    try {
      const created = await api.batches.create(files);
      setBatchId(created.id);
      setBatch({ id: created.id, status: "running", total: created.total, done: 0, items: [] });
    } catch (exc) {
      setError(errorText(exc));
    } finally {
      setCreating(false);
    }
  };

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const status = await api.batches.get(batchId);
        if (cancelled) return;
        setBatch(status);
        if (status.status === "done") {
          if (finishedRef.current !== status.id) {
            finishedRef.current = status.id;
            message.success(`批量处理完成，共 ${status.total} 个文件`);
          }
          return;
        }
        timer = setTimeout(() => void tick(), POLL_INTERVAL);
      } catch (exc) {
        if (cancelled) return;
        setError(errorText(exc));
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [batchId, message]);

  const running = batch !== null && batch.status === "running";
  const percent =
    batch && batch.total > 0 ? Math.min(100, Math.round((batch.done / batch.total) * 100)) : 0;

  const columns: ColumnsType<BatchItem> = [
    {
      title: "序号",
      dataIndex: "id",
      width: 64,
      render: (_value, _record, index) => index + 1,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => {
        const meta = ITEM_STATUS[value] ?? { label: value, color: "default" };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "消息",
      dataIndex: "message",
      render: (value: string) =>
        value ? (
          <Typography.Text type="danger" style={{ fontSize: 12 }}>
            {value}
          </Typography.Text>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      title: "文档 ID",
      dataIndex: "doc_id",
      width: 160,
      render: (value: string | null) =>
        value ? (
          <Tooltip title={value}>
            <span className="mono" style={{ fontSize: 12 }}>
              {shortId(value)}
            </span>
          </Tooltip>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      title: "操作",
      key: "actions",
      width: 140,
      render: (_value, record) => (
        <Button
          type="link"
          size="small"
          disabled={!record.doc_id}
          onClick={() => {
            if (record.doc_id) onOpenDoc(record.doc_id);
          }}
        >
          在工作台打开
        </Button>
      ),
    },
  ];

  return (
    <div className="workbench">
      <Alert
        type="info"
        showIcon
        message="批量任务在后台处理，离开页面不影响执行"
        description="完成后可逐个打开文档，在工作台导出脱敏文件与报告。"
        closable
      />

      <Card size="small" title="选择文件">
        <Upload.Dragger
          accept={ACCEPT}
          multiple
          showUploadList={false}
          disabled={creating || running}
          beforeUpload={(file) => {
            addFiles([file]);
            return false;
          }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽多个文件到此处</p>
          <p className="ant-upload-hint">
            支持 txt / md / log / 代码 / json / csv / eml / docx / pdf / doc，可一次选择多个文件
          </p>
        </Upload.Dragger>

        {files.length > 0 ? (
          <div style={{ marginTop: 12 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 8,
              }}
            >
              <Typography.Text strong>已选择 {files.length} 个文件</Typography.Text>
              <Button
                size="small"
                disabled={creating || running}
                onClick={() => setFiles([])}
              >
                清空
              </Button>
            </div>
            <List
              size="small"
              bordered
              dataSource={files}
              renderItem={(file, index) => (
                <List.Item key={`${file.name}:${file.size}:${file.lastModified}:${index}`}>
                  <Space size={8} style={{ minWidth: 0 }}>
                    <Typography.Text className="ellipsis" style={{ maxWidth: 520 }}>
                      {file.name}
                    </Typography.Text>
                    <span className="text-muted" style={{ fontSize: 12 }}>
                      {formatSize(file.size)}
                    </span>
                  </Space>
                </List.Item>
              )}
            />
          </div>
        ) : null}

        <Space style={{ marginTop: 12 }}>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={creating}
            disabled={files.length === 0 || running || creating}
            onClick={() => void handleStart()}
          >
            开始批量处理
          </Button>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            每次批量任务会自动识别并执行默认脱敏
          </Typography.Text>
        </Space>

        {error ? (
          <Alert
            style={{ marginTop: 12 }}
            type="error"
            showIcon
            message="批量处理请求失败"
            description={error}
          />
        ) : null}
      </Card>

      {batch ? (
        <Card size="small" title="处理进度">
          <Progress
            percent={percent}
            status={batch.status === "done" ? "success" : "active"}
            format={() => `${batch.done} / ${batch.total}`}
          />
          <Table<BatchItem>
            style={{ marginTop: 8 }}
            size="small"
            rowKey="id"
            columns={columns}
            dataSource={batch.items}
            pagination={false}
            locale={{ emptyText: "正在等待后端返回明细…" }}
          />
        </Card>
      ) : null}
    </div>
  );
}
