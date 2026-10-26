import { Tag } from "antd";
import type { DocumentMeta } from "../types";

const STATUS_META: Record<DocumentMeta["status"], { label: string; color: string }> = {
  uploaded: { label: "已上传", color: "default" },
  detected: { label: "已识别", color: "processing" },
  masked: { label: "已脱敏", color: "warning" },
  verified: { label: "已校验", color: "success" },
};

interface StatusTagProps {
  status: DocumentMeta["status"];
}

export default function StatusTag({ status }: StatusTagProps) {
  const meta = STATUS_META[status];
  return <Tag color={meta.color}>{meta.label}</Tag>;
}
