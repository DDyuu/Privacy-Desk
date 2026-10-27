// 导出栏：导出脱敏文件，或用主密码二次确认后导出 JSON/PDF 报告。
import { useEffect, useState } from "react";
import { DownloadOutlined, FilePdfOutlined, FileTextOutlined } from "@ant-design/icons";
import { App, Button, Card, Input, Modal, Space, Tooltip, Typography } from "antd";
import { ApiError, api, errorText, saveBlob } from "../api/client";
import type { DocumentMeta, VerifyResult } from "../types";

type ReportFormat = "json" | "pdf";
type BusyKind = "masked" | "report" | null;

interface ExportBarProps {
  document: DocumentMeta | null;
  verify: VerifyResult | null;
}

function baseName(doc: DocumentMeta): string {
  const suffix = `.${doc.ext}`;
  return doc.name.toLowerCase().endsWith(suffix.toLowerCase())
    ? doc.name.slice(0, -suffix.length)
    : doc.name;
}

// 后端用状态码区分失败原因：401 未带密码、403 密码错误、409 未完成有效脱敏
function exportError(exc: unknown): string {
  if (exc instanceof ApiError) {
    if (exc.status === 401) return "需要主密码";
    if (exc.status === 403) return "密码错误";
    if (exc.status === 409) return exc.message || "尚未完成有效脱敏";
    return exc.message;
  }
  return errorText(exc);
}

export default function ExportBar({ document, verify }: ExportBarProps) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState<BusyKind>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [reportFormat, setReportFormat] = useState<ReportFormat>("json");
  const [password, setPassword] = useState("");

  useEffect(() => {
    // 切换文档时关闭弹窗并清空密码，避免上一份文档输入的密码残留
    setModalOpen(false);
    setPassword("");
  }, [document?.id]);

  const verifyFailed = Boolean(verify && !verify.passed);
  // 校验发现高敏残留时一律禁止导出脱敏文件
  const maskedReady = Boolean(
    document &&
      (document.status === "masked" || document.status === "verified") &&
      !verifyFailed,
  );
  // 报告在脱敏时生成；本次已执行脱敏（即使校验未通过）也可导出
  const reportReady = Boolean(
    document &&
      (document.status === "masked" || document.status === "verified" || verify !== null),
  );

  const maskedDisabledReason = !document
    ? "请先选择文档"
    : verifyFailed
      ? "存在高敏残留，禁止导出"
      : "请先完成识别与脱敏";

  const handleMasked = async () => {
    if (!document) return;
    setBusy("masked");
    try {
      const blob = await api.documents.download(document.id, "masked", "auto");
      saveBlob(blob, `${baseName(document)}_masked.${document.ext}`);
      message.success("已导出脱敏文件");
    } catch (exc) {
      message.error(exportError(exc));
    } finally {
      setBusy(null);
    }
  };

  const openReport = (format: ReportFormat) => {
    // 报告含识别与替换明细，先弹窗收集主密码，确认后才向后端请求
    setReportFormat(format);
    setPassword("");
    setModalOpen(true);
  };

  const handleReport = async () => {
    if (!document) return;
    if (!password) {
      message.warning("请输入主密码");
      return;
    }
    setBusy("report");
    try {
      const blob = await api.documents.download(
        document.id,
        "report",
        reportFormat,
        password,
      );
      saveBlob(blob, `报告.${reportFormat}`);
      message.success("报告已导出");
      setModalOpen(false);
      setPassword("");
    } catch (exc) {
      message.error(exportError(exc));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card size="small" title="导出">
      <Space wrap>
        <Tooltip title={maskedReady ? undefined : maskedDisabledReason}>
          <span style={{ display: "inline-block" }}>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              disabled={!maskedReady}
              loading={busy === "masked"}
              onClick={() => void handleMasked()}
            >
              导出脱敏文件
            </Button>
          </span>
        </Tooltip>
        {/* 两个报告按钮共用 reportReady 可用条件；loading 只跟随当前所选格式，避免同时转圈 */}
        <Tooltip title={reportReady ? undefined : "请先完成识别与脱敏"}>
          <span style={{ display: "inline-block" }}>
            <Button
              icon={<FileTextOutlined />}
              disabled={!reportReady}
              loading={busy === "report" && reportFormat === "json"}
              onClick={() => openReport("json")}
            >
              导出报告 JSON
            </Button>
          </span>
        </Tooltip>
        <Tooltip title={reportReady ? undefined : "请先完成识别与脱敏"}>
          <span style={{ display: "inline-block" }}>
            <Button
              icon={<FilePdfOutlined />}
              disabled={!reportReady}
              loading={busy === "report" && reportFormat === "pdf"}
              onClick={() => openReport("pdf")}
            >
              导出报告 PDF
            </Button>
          </span>
        </Tooltip>
      </Space>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: "10px 0 0" }}>
        导出报告需再次输入主密码；报告包含识别与替换明细。
      </Typography.Paragraph>

      <Modal
        open={modalOpen}
        title="导出报告"
        okText="导出"
        cancelText="取消"
        confirmLoading={busy === "report"}
        onOk={() => void handleReport()}
        onCancel={() => {
          if (busy !== "report") setModalOpen(false);
        }}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          报告格式：{reportFormat.toUpperCase()}。请输入主密码以确认导出。
        </Typography.Paragraph>
        <Input.Password
          autoFocus
          placeholder="主密码"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          onPressEnter={() => void handleReport()}
        />
      </Modal>
    </Card>
  );
}
