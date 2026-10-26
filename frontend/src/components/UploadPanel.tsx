import { useState } from "react";
import { InboxOutlined } from "@ant-design/icons";
import { App, Upload } from "antd";
import { api, errorText } from "../api/client";
import type { DocumentMeta } from "../types";

/** 与后端 ALLOWED_EXTS 保持一致 */
const ACCEPT = ".txt,.md,.log,.py,.java,.js,.ts,.json,.csv,.eml,.docx,.pdf,.doc";

interface UploadPanelProps {
  onUploaded: (doc: DocumentMeta) => void;
}

export default function UploadPanel({ onUploaded }: UploadPanelProps) {
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const doc = await api.documents.upload(file);
      message.success(`已上传：${doc.name}`);
      onUploaded(doc);
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setUploading(false);
    }
  };

  return (
    <Upload.Dragger
      accept={ACCEPT}
      multiple={false}
      showUploadList={false}
      disabled={uploading}
      beforeUpload={(file) => {
        void handleUpload(file);
        return false;
      }}
    >
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">{uploading ? "正在上传…" : "点击或拖拽文件到此处"}</p>
      <p className="ant-upload-hint">支持 txt / md / log / 代码 / json / csv / eml / docx / pdf / doc</p>
    </Upload.Dragger>
  );
}
