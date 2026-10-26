import { useMemo } from "react";
import {
  FileProtectOutlined,
  LockOutlined,
  SettingOutlined,
  TagsOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Tag, Tooltip } from "antd";
import type { SessionStatus } from "../types";

export type PageKey = "workbench" | "batch" | "types" | "settings";

const PAGE_TITLES: Record<PageKey, string> = {
  workbench: "文档脱敏",
  batch: "批量处理",
  types: "类型库",
  settings: "设置",
};

const LLM_TAG: Record<
  SessionStatus["llm_mode"],
  { color: string; label: string; tip: string }
> = {
  online: {
    color: "green",
    label: "在线模型",
    tip: "敏感片段先在本地遮蔽，再调用在线大模型",
  },
  ollama: {
    color: "blue",
    label: "本地 Ollama",
    tip: "使用本机 Ollama 推理，不联网",
  },
  rules: {
    color: "orange",
    label: "离线规则模式",
    tip: "未启用大模型，仅使用本地规则与字典识别",
  },
};

interface AppLayoutProps {
  status: SessionStatus;
  page: PageKey;
  onPageChange: (page: PageKey) => void;
  onLock: () => void;
  children: React.ReactNode;
}

export default function AppLayout({ status, page, onPageChange, onLock, children }: AppLayoutProps) {
  const llm = LLM_TAG[status.llm_mode];

  const menuItems = useMemo(
    () => [
      { key: "workbench", icon: <FileProtectOutlined />, label: "文档脱敏" },
      { key: "batch", icon: <ThunderboltOutlined />, label: "批量处理" },
      { key: "types", icon: <TagsOutlined />, label: "类型库" },
      { key: "settings", icon: <SettingOutlined />, label: "设置" },
    ],
    [],
  );

  return (
    <Layout className="app-shell">
      <Layout.Sider width={208} className="app-sider" theme="light">
        <div className="brand">
          隐盾
          <small>PRIVACY DESK</small>
        </div>
        <Menu
          theme="light"
          mode="inline"
          selectedKeys={[page]}
          items={menuItems}
          onClick={({ key }) => onPageChange(key as PageKey)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="app-header">
          <span className="header-title">{PAGE_TITLES[page]}</span>
          <div className="header-actions">
            <Tooltip title={llm.tip}>
              <Tag color={llm.color}>{llm.label}</Tag>
            </Tooltip>
            <Button icon={<LockOutlined />} onClick={onLock} disabled={!status.unlocked}>
              锁定
            </Button>
          </div>
        </Layout.Header>
        <Layout.Content className="page">{children}</Layout.Content>
      </Layout>
    </Layout>
  );
}
