// 上传面板：拖拽或点击选择单个文件，交给后端解析后回调父级刷新文档列表。
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
      // 上传中禁用拖拽区，防止并发上传打乱列表顺序或超出容量
      disabled={uploading}
      beforeUpload={(file) => {
        // 返回 false 阻止 antd 自身上传，改由这里调用业务接口；不保留文件列表也使同一文件可再次选择
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
