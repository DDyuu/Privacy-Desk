// 应用外壳：左侧菜单 + 顶栏（页面标题/推理模式/锁定），内容区由 App 按 page 注入。
import { useMemo } from "react";
import {
  FileProtectOutlined,
  LockOutlined,
  SettingOutlined,
  TagsOutlined,
  ThunderboltOutlined,
  UnlockOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Tag, Tooltip } from "antd";
import type { SessionStatus } from "../types";

// 菜单页标识；未引入路由库，页面切换完全由 App 的 state 驱动
export type PageKey = "workbench" | "batch" | "types" | "reveal" | "settings";

const PAGE_TITLES: Record<PageKey, string> = {
  workbench: "文档脱敏",
  batch: "批量处理",
  types: "类型库",
  reveal: "解密 ENC",
  settings: "设置",
};

// 三种推理模式的标签配色与说明集中维护，避免各页面重复判断
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

  // 菜单结构固定，只构建一次；选中态由 selectedKeys 跟随 page
  const menuItems = useMemo(
    () => [
      { key: "workbench", icon: <FileProtectOutlined />, label: "文档脱敏" },
      { key: "batch", icon: <ThunderboltOutlined />, label: "批量处理" },
      { key: "types", icon: <TagsOutlined />, label: "类型库" },
      { key: "reveal", icon: <UnlockOutlined />, label: "解密 ENC" },
      { key: "settings", icon: <SettingOutlined />, label: "设置" },
    ],
    [],
  );

  return (
    <Layout className="app-shell">
      {/* 侧栏固定 208px，页面滚动只发生在内容区 */}
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
            {/* 模式标签提示当前数据是否离开本机，悬停可看说明 */}
            <Tooltip title={llm.tip}>
              <Tag color={llm.color}>{llm.label}</Tag>
            </Tooltip>
            {/* 未解锁时禁用，避免无意义地调用锁定接口 */}
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
