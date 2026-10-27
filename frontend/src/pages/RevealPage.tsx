// 解密页：选择已脱敏文档，二次输入主密码后还原 ENC 令牌明文，结果只在本页展示
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Typography,
} from "antd";
import type { TableProps } from "antd";
import { api, errorText } from "../api/client";
import type { DocumentMeta, RevealedItem, TypeDefinition } from "../types";

interface RevealPageProps {
  byCode: Record<string, TypeDefinition>;
}

export default function RevealPage({ byCode }: RevealPageProps) {
  const { message } = App.useApp();
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [docId, setDocId] = useState<string>();
  const [password, setPassword] = useState("");
  const [revealing, setRevealing] = useState(false);
  const [items, setItems] = useState<RevealedItem[]>([]);
  const [revealedName, setRevealedName] = useState("");

  useEffect(() => {
    api.documents
      .list()
      .then((docs) => {
        setDocuments(
          // 只有已脱敏/已校验的文档才可能包含可解密的 ENC 令牌，其余文档不列出
          docs.filter((doc) => doc.status === "masked" || doc.status === "verified"),
        );
      })
      .catch((exc) => message.error(errorText(exc)))
      .finally(() => setLoading(false));
  }, [message]);

  const options = useMemo(
    () => documents.map((doc) => ({ value: doc.id, label: `${doc.name}（${doc.ext}）` })),
    [documents],
  );

  const handleReveal = async () => {
    // 主密码不落盘，解密时必须再次输入并交给后端校验，成功后才返回明文
    if (!docId) {
      message.warning("请先选择文档");
      return;
    }
    if (!password) {
      message.warning("请输入主密码");
      return;
    }
    setRevealing(true);
    try {
      const result = await api.documents.reveal(docId, password);
      setItems(result.items);
      setRevealedName(options.find((item) => item.value === docId)?.label ?? "");
      setPassword("");
      message.success(
        result.items.length > 0
          ? `已解密 ${result.items.length} 个令牌`
          : "该文档没有加密令牌",
      );
    } catch (exc) {
      message.error(errorText(exc));
    } finally {
      setRevealing(false);
    }
  };

  const columns: TableProps<RevealedItem>["columns"] = [
    {
      title: "类型",
      dataIndex: "type_code",
      width: 160,
      render: (code: string) => byCode[code]?.name ?? code,
    },
    {
      title: "原文片段",
      dataIndex: "text",
      render: (text: string) => <span className="mono">{text}</span>,
    },
  ];

  return (
    <div style={{ maxWidth: 900 }}>
      <Card size="small" title="解密 ENC 令牌">
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            style={{ width: 320 }}
            placeholder="选择已脱敏的文档"
            loading={loading}
            value={docId}
            options={options}
            onChange={(value) => {
              setDocId(value);
              setItems([]);
            }}
            showSearch
            optionFilterProp="label"
          />
          <Input.Password
            style={{ width: 220 }}
            placeholder="主密码"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onPressEnter={() => void handleReveal()}
          />
          <Button type="primary" loading={revealing} onClick={() => void handleReveal()}>
            解密
          </Button>
        </Space>

        <Alert
          type="info"
          showIcon
          message="仅解密使用「加密」方式处理的片段；需要再次输入主密码，结果只在当前页面展示。"
        />

        {loading ? (
          <div style={{ padding: 24, textAlign: "center" }}>
            <Spin />
          </div>
        ) : documents.length === 0 ? (
          <div style={{ padding: 24 }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无可解密的文档，请先完成脱敏"
            />
          </div>
        ) : null}

        {items.length > 0 ? (
          <>
            <Typography.Text type="secondary" style={{ display: "block", margin: "16px 0 8px" }}>
              {revealedName}：共 {items.length} 个明文片段
            </Typography.Text>
            {/* 解密结果只在当前页面展示，切换文档会清空 items */}
            <Table
              rowKey={(item) => `${item.type_code}-${item.start}`}
              size="small"
              columns={columns}
              dataSource={items}
              pagination={false}
            />
          </>
        ) : null}
      </Card>
    </div>
  );
}
