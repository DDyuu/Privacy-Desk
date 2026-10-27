// 文档状态标签：把后端状态映射为中文文案与固定颜色，供列表等处复用。
import { Tag } from "antd";
import type { DocumentMeta } from "../types";

// 颜色随流程递进：默认灰 → 处理中蓝 → 待确认橙 → 成功绿，避免同一状态在不同页面颜色不一致
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
