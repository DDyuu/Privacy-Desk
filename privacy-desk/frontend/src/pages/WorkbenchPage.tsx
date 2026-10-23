import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ReloadOutlined, SaveOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { App, Button, Card, Input, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import { api, errorText } from "../api/client";
import CompareView from "../components/CompareView";
import DetectionTable from "../components/DetectionTable";
import DocumentList from "../components/DocumentList";
import ExportBar from "../components/ExportBar";
import MaskPanel from "../components/MaskPanel";
import StatusTag from "../components/StatusTag";
import UploadPanel from "../components/UploadPanel";
import type {
  AppliedItem,
  DocumentDetail,
  DocumentMeta,
  MaskActions,
  MaskStats,
  SessionStatus,
  Span,
  TypeDefinition,
  VerifyResult,
} from "../types";

const MODE_META: Record<SessionStatus["llm_mode"], { label: string; color: string }> = {
  rules: { label: "规则模式", color: "orange" },
  online: { label: "在线模型", color: "green" },
  ollama: { label: "本地 Ollama", color: "blue" },
};

interface WorkbenchPageProps {
  byCode: Record<string, TypeDefinition>;
  llmMode: SessionStatus["llm_mode"];
  /** 由外部（如批量页）指定要打开的文档 */
  openDocId?: string | null;
  /** 文档选中后清除外部指定 */
  onOpenedDoc?: () => void;
}

export default function WorkbenchPage({
  byCode,
  llmMode,
  openDocId = null,
  onOpenedDoc,
}: WorkbenchPageProps) {
  const { message } = App.useApp();

  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [text, setText] = useState("");
  const [spans, setSpans] = useState<Span[]>([]);
  const [mode, setMode] = useState<string | null>(null);
  const [maskedText, setMaskedText] = useState<string | null>(null);
  const [applied, setApplied] = useState<AppliedItem[]>([]);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [maskStats, setMaskStats] = useState<MaskStats | null>(null);
  const [activeTab, setActiveTab] = useState("detection");
  const [detecting, setDetecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [masking, setMasking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const compareRef = useRef<HTMLDivElement>(null);
  const selectedIdRef = useRef<string | null>(selectedId);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    if (!openDocId) return;
    setSelectedId(openDocId);
    onOpenedDoc?.();
  }, [openDocId, onOpenedDoc]);

  const currentMode: SessionStatus["llm_mode"] =
    mode === "online" || mode === "ollama" || mode === "rules" ? mode : llmMode;

  const loadDocuments = useCallback(async () => {
    setListLoading(true);
    try {
      setDocuments(await api.documents.list());
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setListLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setText("");
      setSpans([]);
      setMaskedText(null);
      setApplied([]);
      setVerify(null);
      setMaskStats(null);
      setMode(null);
      return;
    }

    let cancelled = false;
    setDetailLoading(true);
    setDetail(null);
    setText("");
    setSpans([]);
    setMaskedText(null);
    setApplied([]);
    setVerify(null);
    setMaskStats(null);
    setMode(null);

    api.documents
      .get(selectedId)
      .then(async (doc) => {
        if (cancelled) return;
        setDetail(doc);
        setText(doc.text);
        setSpans(doc.detections);
        if (doc.status === "masked" || doc.status === "verified") {
          try {
            const comparison = await api.documents.compare(doc.id);
            if (cancelled) return;
            setMaskedText(comparison.masked);
            setApplied(comparison.applied ?? []);
            setVerify(comparison.verify ?? null);
          } catch {
            /* 历史脱敏结果不可读时不阻塞编辑 */
          }
        }
      })
      .catch((exc) => {
        if (!cancelled) message.error(errorText(exc));
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId, message]);

  useEffect(() => {
    if (maskedText !== null) {
      compareRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [maskedText, verify]);

  const clearMask = () => {
    setMaskedText(null);
    setApplied([]);
    setVerify(null);
    setMaskStats(null);
  };

  const selectedDoc: DocumentMeta | null =
    detail && detail.id === selectedId
      ? detail
      : documents.find((item) => item.id === selectedId) ?? null;

  const dirty = Boolean(detail && text !== detail.text);
  const ruleCount = useMemo(
    () => spans.filter((span) => span.source === "rule").length,
    [spans],
  );
  const llmCount = spans.length - ruleCount;
  const canMask = Boolean(
    detail &&
      detail.status !== "uploaded" &&
      spans.length > 0 &&
      !dirty &&
      !detecting &&
      !saving,
  );

  const handleUploaded = (doc: DocumentMeta) => {
    setDocuments((prev) => [doc, ...prev.filter((item) => item.id !== doc.id)]);
    setSelectedId(doc.id);
    void loadDocuments();
  };

  const handleDetect = async () => {
    if (!selectedId) return;
    const docId = selectedId;
    setDetecting(true);
    try {
      const result = await api.documents.detect(docId, true);
      void loadDocuments();
      if (selectedIdRef.current !== docId) return;
      setSpans(result.spans);
      setMode(result.mode);
      clearMask();
      setActiveTab("detection");
      const updated = await api.documents.get(docId).catch(() => null);
      if (selectedIdRef.current !== docId) return;
      if (updated) {
        setDetail(updated);
        setText(updated.text);
      }
      message.success(
        result.spans.length > 0
          ? `识别完成，共 ${result.spans.length} 处敏感信息`
          : "识别完成，未发现敏感信息",
      );
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setDetecting(false);
    }
  };

  const handleSaveText = async () => {
    if (!selectedId || !detail) return;
    const docId = selectedId;
    setSaving(true);
    try {
      await api.documents.saveText(docId, text);
      void loadDocuments();
      if (selectedIdRef.current !== docId) return;
      setSpans([]);
      setMode(null);
      clearMask();
      setActiveTab("detection");
      setDetail((prev) =>
        prev ? { ...prev, text, status: "uploaded", detections: [] } : prev,
      );
      const updated = await api.documents.get(docId).catch(() => null);
      if (selectedIdRef.current !== docId) return;
      if (updated) setDetail(updated);
      message.success("已保存，请重新识别");
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setSaving(false);
    }
  };

  const handleMask = async (actions: MaskActions) => {
    if (!selectedId) return;
    if (!canMask) {
      message.warning("请先保存修改并完成识别，再执行脱敏");
      return;
    }
    const docId = selectedId;
    setMasking(true);
    try {
      const result = await api.documents.mask(docId, actions, true);
      void loadDocuments();
      const updated = await api.documents.get(docId).catch(() => null);
      if (selectedIdRef.current !== docId) return;
      setMaskedText(result.masked_text);
      setApplied(result.applied);
      setVerify(result.verify);
      setMaskStats(result.stats);
      if (updated) setDetail(updated);
      if (result.verify && !result.verify.passed) {
        message.warning("脱敏完成，但校验未通过，请调整配置后重试");
      } else {
        message.success("脱敏完成，校验通过");
      }
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setMasking(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const docId = selectedId;
      await loadDocuments();
      if (docId) {
        const doc = await api.documents.get(docId);
        if (selectedIdRef.current !== docId) return;
        const textChanged = doc.text !== text;
        setDetail(doc);
        if (textChanged) {
          setText(doc.text);
          setSpans(doc.detections);
          clearMask();
        }
      }
      message.success("已刷新");
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="workbench">
      <Card size="small" bodyStyle={{ padding: 12 }}>
        <div className="workbench-toolbar-row">
          <Space size={8} wrap>
            <Typography.Text strong>{detail?.name ?? "未选择文档"}</Typography.Text>
            {detail ? <StatusTag status={detail.status} /> : null}
            <Tooltip title={`当前模式：${currentMode}`}>
              <Tag color={MODE_META[currentMode].color}>{MODE_META[currentMode].label}</Tag>
            </Tooltip>
          </Space>
          <Space size={8} wrap>
            <Tooltip title={dirty ? "请先保存修改再识别" : undefined}>
              <span style={{ display: "inline-block" }}>
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  loading={detecting}
                  disabled={!selectedId || detailLoading || saving || masking || dirty}
                  onClick={() => void handleDetect()}
                >
                  识别
                </Button>
              </span>
            </Tooltip>
            <Button
              icon={<SaveOutlined />}
              loading={saving}
              disabled={!detail || !dirty || detecting || masking}
              onClick={() => void handleSaveText()}
            >
              保存修改
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={refreshing}
              disabled={refreshing || detecting || saving || masking}
              onClick={() => void handleRefresh()}
            >
              刷新
            </Button>
          </Space>
        </div>
        <div className="stat-bar">
          <span>识别总数 {spans.length}</span>
          <span>规则 {ruleCount}</span>
          <span>LLM {llmCount}</span>
          <span>当前模式 {MODE_META[currentMode].label}</span>
        </div>
      </Card>

      <div className="workbench-grid">
        <div className="workbench-left">
          <Card size="small" title="上传文档">
            <UploadPanel onUploaded={handleUploaded} />
          </Card>
          <DocumentList
            documents={documents}
            selectedId={selectedId}
            loading={listLoading}
            onSelect={setSelectedId}
          />
        </div>

        <Card
          size="small"
          title="原文编辑"
          extra={
            dirty ? (
              <Tag color="orange">未保存</Tag>
            ) : (
              <span className="text-muted">字符数 {text.length}</span>
            )
          }
        >
          <Input.TextArea
            className="mono"
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={!detail || detailLoading || detecting || saving || masking}
            placeholder="请选择左侧文档，或先上传文件"
            style={{ minHeight: 460, fontSize: 13, lineHeight: 1.8 }}
          />
        </Card>

        <Card size="small" bodyStyle={{ padding: 12 }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: "detection",
                label: `识别结果${spans.length > 0 ? ` (${spans.length})` : ""}`,
                children: (
                  <DetectionTable spans={spans} byCode={byCode} loading={detecting} />
                ),
              },
              {
                key: "mask",
                label: "脱敏配置",
                children: (
                  <MaskPanel
                    spans={spans}
                    byCode={byCode}
                    disabled={!canMask}
                    loading={masking}
                    verify={verify}
                    stats={maskStats}
                    onMask={(actions) => void handleMask(actions)}
                  />
                ),
              },
            ]}
          />
        </Card>
      </div>

      <div ref={compareRef}>
        {maskedText !== null ? (
          <CompareView
            original={detail?.text ?? text}
            masked={maskedText}
            spans={spans}
            applied={applied}
            byCode={byCode}
          />
        ) : null}
      </div>

      <ExportBar document={selectedDoc} verify={verify} />
    </div>
  );
}
