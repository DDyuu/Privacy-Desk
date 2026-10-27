import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { App, Button, Card, Empty, Space, Steps, Tag, Tooltip, Typography } from "antd";
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

type Stage = "detection" | "mask" | "compare";

const spanKey = (span: Span) => `${span.start}-${span.end}-${span.type_code}`;

const STAGE_INDEX: Record<Stage, number> = { detection: 0, mask: 1, compare: 2 };
const STAGE_ORDER: Stage[] = ["detection", "mask", "compare"];
const STAGE_TITLE: Record<Stage, string> = {
  detection: "识别结果",
  mask: "脱敏配置",
  compare: "脱敏对比",
};

interface WorkbenchPageProps {
  byCode: Record<string, TypeDefinition>;
  llmMode: SessionStatus["llm_mode"];
  maxDocs?: number;
  /** 由外部（如批量页）指定要打开的文档 */
  openDocId?: string | null;
  /** 文档选中后清除外部指定 */
  onOpenedDoc?: () => void;
}

export default function WorkbenchPage({
  byCode,
  llmMode,
  maxDocs,
  openDocId = null,
  onOpenedDoc,
}: WorkbenchPageProps) {
  const { message } = App.useApp();

  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [spans, setSpans] = useState<Span[]>([]);
  const [ignoredKeys, setIgnoredKeys] = useState<string[]>([]);
  const [mode, setMode] = useState<string | null>(null);
  const [maskedText, setMaskedText] = useState<string | null>(null);
  const [applied, setApplied] = useState<AppliedItem[]>([]);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [maskStats, setMaskStats] = useState<MaskStats | null>(null);
  const [stage, setStage] = useState<Stage>("detection");
  const [detecting, setDetecting] = useState(false);
  const [masking, setMasking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [clearing, setClearing] = useState(false);

  const selectedIdRef = useRef<string | null>(selectedId);
  const autoDetectedRef = useRef<Set<string>>(new Set());

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

  const clearMask = () => {
    setMaskedText(null);
    setApplied([]);
    setVerify(null);
    setMaskStats(null);
  };

  const handleClearDocuments = async () => {
    setClearing(true);
    try {
      const result = await api.documents.clear();
      setSelectedId(null);
      setDetail(null);
      setSpans([]);
      setIgnoredKeys([]);
      setMode(null);
      clearMask();
      setStage("detection");
      setDocuments([]);
      autoDetectedRef.current.clear();
      message.success(`已清空 ${result.deleted} 份历史文档`);
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setClearing(false);
    }
  };

  const runDetect = async (docId: string): Promise<boolean> => {
    setDetecting(true);
    try {
      const result = await api.documents.detect(docId, true);
      void loadDocuments();
      if (selectedIdRef.current !== docId) return true;
      setSpans(result.spans);
      setIgnoredKeys([]);
      setMode(result.mode);
      clearMask();
      setStage("detection");
      const updated = await api.documents.get(docId).catch(() => null);
      if (selectedIdRef.current !== docId) return true;
      if (updated) setDetail(updated);
      message.success(
        result.spans.length > 0
          ? `识别完成，共 ${result.spans.length} 处敏感信息`
          : "识别完成，未发现敏感信息",
      );
      return true;
    } catch (exc) {
      message.error(errorText(exc));
      return false;
    } finally {
      setDetecting(false);
    }
  };

  /** 上传后或打开未识别文档时自动执行识别，同一文档只自动触发一次 */
  const autoDetect = (doc: DocumentDetail) => {
    if (doc.status !== "uploaded" || autoDetectedRef.current.has(doc.id)) return;
    autoDetectedRef.current.add(doc.id);
    void runDetect(doc.id).then((ok) => {
      if (!ok) autoDetectedRef.current.delete(doc.id);
    });
  };

  const loadComparison = useCallback(
    async (docId: string): Promise<boolean> => {
      try {
        const comparison = await api.documents.compare(docId);
        if (selectedIdRef.current !== docId) return false;
        setMaskedText(comparison.masked);
        setApplied(comparison.applied ?? []);
        setVerify(comparison.verify ?? null);
        setIgnoredKeys(comparison.ignored ?? []);
        return true;
      } catch {
        return false;
      }
    },
    [],
  );

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setSpans([]);
      setIgnoredKeys([]);
      clearMask();
      setMode(null);
      setStage("detection");
      return;
    }

    let cancelled = false;
    setDetail(null);
    setSpans([]);
    setIgnoredKeys([]);
    clearMask();
    setMode(null);
    setStage("detection");

    api.documents
      .get(selectedId)
      .then(async (doc) => {
        if (cancelled) return;
        setDetail(doc);
        setSpans(doc.detections);
        if (doc.status === "masked" || doc.status === "verified") {
          const restored = await loadComparison(doc.id);
          if (!cancelled && restored) setStage("compare");
        } else {
          autoDetect(doc);
        }
      })
      .catch((exc) => {
        if (!cancelled) message.error(errorText(exc));
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId, message, loadComparison]);

  const selectedDoc: DocumentMeta | null =
    detail && detail.id === selectedId
      ? detail
      : documents.find((item) => item.id === selectedId) ?? null;

  const ruleCount = useMemo(
    () => spans.filter((span) => span.source === "rule").length,
    [spans],
  );
  const llmCount = spans.length - ruleCount;
  const ignoredSet = useMemo(() => new Set(ignoredKeys), [ignoredKeys]);
  const activeSpans = useMemo(
    () => spans.filter((span) => !ignoredSet.has(spanKey(span))),
    [spans, ignoredSet],
  );
  const canMask = Boolean(
    detail && detail.status !== "uploaded" && activeSpans.length > 0 && !detecting,
  );

  const handleUploaded = (doc: DocumentMeta) => {
    setDocuments((prev) => [doc, ...prev.filter((item) => item.id !== doc.id)]);
    setSelectedId(doc.id);
    void loadDocuments();
  };

  const toggleIgnore = (span: Span) => {
    const key = spanKey(span);
    setIgnoredKeys((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key],
    );
  };

  /** 步骤条只允许回退：对比 → 配置/识别，配置 → 识别；前进仍由底部按钮触发 */
  const handleStageChange = (next: number) => {
    const target = STAGE_ORDER[next];
    if (!target || STAGE_INDEX[target] >= STAGE_INDEX[stage]) return;
    if (target === "mask" && activeSpans.length === 0) return;
    setStage(target);
  };

  const handleMask = async (actions: MaskActions) => {
    if (!selectedId) return;
    if (!canMask) {
      message.warning("请先完成识别，再执行脱敏");
      return;
    }
    const docId = selectedId;
    setMasking(true);
    try {
      const result = await api.documents.mask(docId, actions, true, ignoredKeys);
      void loadDocuments();
      const updated = await api.documents.get(docId).catch(() => null);
      if (selectedIdRef.current !== docId) return;
      setMaskedText(result.masked_text);
      setApplied(result.applied);
      setVerify(result.verify);
      setMaskStats(result.stats);
      if (updated) setDetail(updated);
      setStage("compare");
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
        setDetail(doc);
        setSpans(doc.detections);
        if (doc.status === "masked" || doc.status === "verified") {
          const restored = await loadComparison(docId);
          if (selectedIdRef.current !== docId) return;
          if (restored) {
            setStage("compare");
          } else {
            clearMask();
            setStage("detection");
          }
        } else {
          clearMask();
          setStage("detection");
          autoDetect(doc);
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
            <Button
              icon={<ReloadOutlined />}
              loading={refreshing}
              disabled={refreshing || detecting || masking}
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
            maxDocs={maxDocs}
            clearing={clearing}
            onClear={() => void handleClearDocuments()}
            onSelect={setSelectedId}
          />
        </div>

        <Card
          size="small"
          className="workbench-main"
          title={STAGE_TITLE[stage]}
          extra={
            stage === "compare" ? (
              <Button size="small" onClick={() => setStage("mask")} disabled={masking}>
                重新配置
              </Button>
            ) : stage === "mask" ? (
              <Button size="small" type="text" onClick={() => setStage("detection")}>
                返回识别结果
              </Button>
            ) : null
          }
          bodyStyle={{ padding: 12 }}
        >
          <Steps
            size="small"
            current={STAGE_INDEX[stage]}
            onChange={handleStageChange}
            items={[
              { title: "识别" },
              { title: "脱敏配置", disabled: STAGE_INDEX[stage] < STAGE_INDEX.mask },
              { title: "脱敏对比", disabled: STAGE_INDEX[stage] < STAGE_INDEX.compare },
            ]}
            style={{ marginBottom: 16 }}
          />

          <div className="workbench-stage">
            <div style={{ display: stage === "detection" ? undefined : "none" }}>
              <DetectionTable
                spans={spans}
                byCode={byCode}
                loading={detecting}
                ignoredKeys={ignoredKeys}
                onToggleIgnore={toggleIgnore}
              />
            </div>

            <div style={{ display: stage === "mask" ? undefined : "none" }}>
              <MaskPanel
                spans={activeSpans}
                byCode={byCode}
                disabled={!canMask}
                loading={masking}
                verify={verify}
                stats={maskStats}
                onMask={(actions) => void handleMask(actions)}
              />
            </div>

            <div style={{ display: stage === "compare" ? undefined : "none" }}>
              {maskedText !== null ? (
                <CompareView
                  embedded
                  original={detail?.text ?? ""}
                  masked={maskedText}
                  spans={spans}
                  applied={applied}
                  byCode={byCode}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未生成脱敏结果" />
              )}
            </div>
          </div>

          {stage === "detection" ? (
            <Space className="workbench-footer" wrap>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                disabled={!canMask}
                onClick={() => setStage("mask")}
              >
                执行脱敏
              </Button>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                下一步可为每种类型选择屏蔽、替换、模糊化或加密
              </Typography.Text>
            </Space>
          ) : null}
        </Card>
      </div>

      <ExportBar document={selectedDoc} verify={verify} />
    </div>
  );
}
