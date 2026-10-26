# 隐私脱敏系统桌面端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为已完成的后端实现 Electron + React 桌面端：主密码门禁、文档工作台、识别结果、脱敏配置、前后对比、批量、类型管理、设置，并产出 Windows 安装包与使用说明。

**Architecture:** Electron 主进程以随机端口和一次性令牌启动 FastAPI sidecar；渲染进程为 React 18 + Ant Design 5，通过 `window.privacyDesk` 获取 API 地址与令牌；生产环境加载 `frontend/dist/index.html`，后端只提供 API。

**Tech Stack:** React 18、TypeScript、Vite、Ant Design 5、@ant-design/icons、Electron 33、electron-builder、PyInstaller、PowerShell 构建脚本。

**后端契约（已完成，界面必须按此对接）：**
- 会话：`GET/POST /api/v1/session/status|setup|unlock|lock`
- 文档：`POST/GET /api/v1/documents`、`GET/PUT /documents/{id}`、`PUT /{id}/content`、`POST /{id}/detect`、`POST /{id}/mask`、`POST /{id}/verify`、`GET /{id}/compare`、`GET /{id}/export?kind=masked|report&fmt=auto|json|pdf&password=`
- 类型：`GET /api/v1/types`、`PUT /types/{code}`、`DELETE /types/{code}`、`POST /types/test`
- 设置：`GET/PUT /api/v1/settings/llm`、`POST /settings/llm/test`
- 批量：`POST /api/v1/batches`、`GET /batches/{id}`
- Span 字段：`start,end,type_code,text,confidence,source,level`
- 文档状态：`uploaded/detected/masked/verified`；mask 前必须 detect；导出 masked 要求状态不是 uploaded/detected；报告导出需要二次主密码。

**执行约定：** 工作目录 `privacy-desk/`；不要执行 git（用户要求人工审核后提交）；每完成一个 Task 跑 `npm run build` 或对应验收命令。

---

## 文件结构

```
privacy-desk/
├─ frontend/
│  ├─ package.json
│  ├─ vite.config.ts
│  ├─ tsconfig.json
│  ├─ index.html
│  └─ src/
│     ├─ main.tsx
│     ├─ App.tsx
│     ├─ styles.css
│     ├─ types.ts
│     ├─ api/client.ts
│     ├─ components/{Layout,UploadPanel,DocumentList,DetectionTable,MaskPanel,CompareView,ExportBar,TypeTag,StatusTag}.tsx
│     ├─ pages/{LockPage,WorkbenchPage,BatchPage,TypesPage,SettingsPage}.tsx
│     └─ hooks/{useSession,useTypes,useIdleLock}.ts
├─ electron/
│  ├─ main.cjs
│  └─ preload.cjs
├─ backend/（已完成）
├─ scripts/build.ps1
├─ electron-builder.yml
└─ README.md（使用说明）
```

---

## Task 1: 前端脚手架

**Files:**
- Create: `frontend/package.json`、`vite.config.ts`、`tsconfig.json`、`index.html`
- Create: `frontend/src/main.tsx`、`App.tsx`、`styles.css`
- Create: `frontend/src/types.ts`

- [ ] **Step 1: 初始化依赖**

`package.json` 关键内容：

```json
{
  "name": "privacy-desk-ui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "electron:dev": "concurrently -k \"npm:dev\" \"cross-env VITE_DEV_SERVER=http://localhost:5173 electron ../electron/main.cjs\""
  },
  "dependencies": {
    "@ant-design/icons": "^5.5.1",
    "antd": "^5.21.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "concurrently": "^9.0.1",
    "cross-env": "^7.0.3",
    "electron": "^33.0.0",
    "typescript": "^5.6.2",
    "vite": "^5.4.8"
  }
}
```

`vite.config.ts`：

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { port: 5173, strictPort: true },
  build: { outDir: "dist", emptyOutDir: true },
});
```

`tsconfig.json`：`target ES2022`、`jsx react-jsx`、`moduleResolution bundler`、`strict true`、`noEmit true`。

`index.html` 增加 CSP（允许本地 API 与 Vite HMR）：

```html
<meta http-equiv="Content-Security-Policy"
  content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self' http://127.0.0.1:* http://localhost:* ws://localhost:*" />
```

`src/types.ts`：

```ts
export type Level = "high" | "medium" | "low";
export type Action = "mask" | "replace" | "fuzz" | "encrypt";

export interface Span {
  start: number;
  end: number;
  type_code: string;
  text: string;
  confidence: number;
  source: "rule" | "llm";
  level: Level;
}

export interface DocumentMeta {
  id: string;
  name: string;
  ext: string;
  size: number;
  status: "uploaded" | "detected" | "masked" | "verified";
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentMeta {
  text: string;
  detections: Span[];
}

export interface TypeDefinition {
  code: string;
  name: string;
  category: string;
  level: Level;
  builtin: boolean;
  enabled: boolean;
  detectors: Array<{
    kind: "regex" | "checksum" | "keyword" | "dict" | "llm";
    pattern?: string;
    flags?: string[];
    algo?: string;
    words?: string[];
    hint?: string;
  }>;
  defaultAction: Action;
  actionOptions: Record<string, number>;
}

export interface VerifyResult {
  passed: boolean;
  residuals: Span[];
  metrics: Record<string, number>;
  issues: string[];
}

export interface SessionStatus {
  initialized: boolean;
  unlocked: boolean;
  llm_mode: "online" | "ollama" | "rules";
}

export interface LLMConfig {
  mode: "online" | "ollama" | "rules";
  base_url: string;
  model: string;
  api_key: string;
  ollama_url: string;
  ollama_model: string;
  has_key?: boolean;
}

export interface BatchStatus {
  id: string;
  status: "running" | "done";
  total: number;
  done: number;
  items: Array<{ id: string; doc_id: string | null; status: string; message: string }>;
}
```

- [ ] **Step 2: 全局样式与入口**

`styles.css` 定义：

```css
:root {
  --brand: #0f766e;
  --ink: #0b1220;
  --muted: #64748b;
  --bg: #f5f7fa;
  --panel: #ffffff;
  --border: #e2e8f0;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif; }
.app-shell { min-height: 100vh; }
.app-sider { background: var(--ink) !important; }
.brand { color: #fff; font-size: 18px; font-weight: 700; letter-spacing: 1px; padding: 18px 20px; }
.brand small { display: block; color: #94a3b8; font-weight: 400; font-size: 11px; letter-spacing: 2px; }
.page { padding: 20px 24px; }
.mono { font-family: Consolas, "JetBrains Mono", monospace; }
.compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.compare-pane { background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 14px; height: 480px; overflow: auto; white-space: pre-wrap; line-height: 1.9; }
mark.hit-high { background: #fee2e2; color: #991b1b; border-radius: 3px; }
mark.hit-medium { background: #fef3c7; color: #92400e; border-radius: 3px; }
mark.hit-low { background: #e0f2fe; color: #075985; border-radius: 3px; }
.stat-bar { display: flex; gap: 20px; color: var(--muted); font-size: 13px; }
```

`src/main.tsx` 用 `ConfigProvider` 主题（primary `#0f766e`、圆角 8）渲染 `App`。

- [ ] **Step 3: 验收**

Run: `npm install`，然后 `npm run build`。
Expected: 构建成功，生成 `frontend/dist/index.html`。

---

## Task 2: API 客户端

**Files:**
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: 实现**

```ts
import type {
  BatchStatus, DocumentDetail, DocumentMeta, LLMConfig, SessionStatus, Span, TypeDefinition, VerifyResult,
} from "../types";

declare global {
  interface Window {
    privacyDesk?: { apiBase: string; token: string };
  }
}

const API_BASE =
  window.privacyDesk?.apiBase ??
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://127.0.0.1:8765";
const APP_TOKEN =
  window.privacyDesk?.token ?? (import.meta.env.VITE_APP_TOKEN as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function headers(json = true): Record<string, string> {
  const value: Record<string, string> = {};
  if (APP_TOKEN) value["X-App-Token"] = APP_TOKEN;
  if (json) value["Content-Type"] = "application/json";
  return value;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: { ...headers(!(init.body instanceof FormData)), ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  session: {
    status: () => request<SessionStatus>("/session/status"),
    setup: (password: string) =>
      request<SessionStatus>("/session/setup", { method: "POST", body: JSON.stringify({ password }) }),
    unlock: (password: string) =>
      request<SessionStatus>("/session/unlock", { method: "POST", body: JSON.stringify({ password }) }),
    lock: () => request<SessionStatus>("/session/lock", { method: "POST" }),
  },
  documents: {
    list: () => request<DocumentMeta[]>("/documents"),
    get: (id: string) => request<DocumentDetail>(`/documents/${id}`),
    upload: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return request<DocumentMeta>("/documents", { method: "POST", body: form });
    },
    saveText: (id: string, text: string) =>
      request<{ id: string; length: number }>(`/documents/${id}/content`, {
        method: "PUT",
        body: JSON.stringify({ text }),
      }),
    detect: (id: string, useLlm = true) =>
      request<{ spans: Span[]; mode: string; text_length: number }>(`/documents/${id}/detect`, {
        method: "POST",
        body: JSON.stringify({ use_llm: useLlm }),
      }),
    mask: (id: string, actions: Record<string, { action: string; options?: Record<string, number> }>, verify = true) =>
      request<{
        masked_text: string; applied: Array<Record<string, unknown>>; stats: Record<string, number>;
        verify: VerifyResult | null; summary: Record<string, unknown>; job_id: string;
      }>(`/documents/${id}/mask`, {
        method: "POST",
        body: JSON.stringify({ actions, verify }),
      }),
    verify: (id: string) => request<VerifyResult>(`/documents/${id}/verify`, { method: "POST" }),
    compare: (id: string) =>
      request<{ original: string; masked: string; detections: Span[] }>(`/documents/${id}/compare`),
    download: async (id: string, kind: "masked" | "report", fmt: string, password?: string) => {
      const query = new URLSearchParams({ kind, fmt });
      if (password) query.set("password", password);
      const response = await fetch(`${API_BASE}/api/v1/documents/${id}/export?${query}`, {
        headers: headers(false),
      });
      if (!response.ok) {
        let detail = response.statusText;
        try {
          detail = (await response.json()).detail ?? detail;
        } catch {
          /* ignore */
        }
        throw new ApiError(response.status, detail);
      }
      return await response.blob();
    },
  },
  types: {
    list: () => request<TypeDefinition[]>("/types"),
    save: (payload: TypeDefinition) =>
      request<TypeDefinition>(`/types/${payload.code}`, { method: "PUT", body: JSON.stringify(payload) }),
    remove: (code: string) => request<{ deleted: string }>(`/types/${code}`, { method: "DELETE" }),
    test: (type: TypeDefinition, samples: string[]) =>
      request<{ results: Array<{ sample: string; spans: Span[] }> }>("/types/test", {
        method: "POST",
        body: JSON.stringify({ type, samples }),
      }),
  },
  settings: {
    getLlm: () => request<LLMConfig>("/settings/llm"),
    saveLlm: (config: LLMConfig) =>
      request<LLMConfig>("/settings/llm", { method: "PUT", body: JSON.stringify(config) }),
    testLlm: () => request<{ ok: boolean; mode: string; latency_ms?: number; items?: number; message?: string }>(
      "/settings/llm/test",
      { method: "POST" },
    ),
  },
  batches: {
    create: (files: File[]) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      return request<{ id: string; total: number }>("/batches", { method: "POST", body: form });
    },
    get: (id: string) => request<BatchStatus>(`/batches/${id}`),
  },
};

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 2: 验收**

`npm run build` 通过，无 TypeScript 错误。

---

## Task 3: 应用外壳、会话门禁与自动锁定

**Files:**
- Create: `frontend/src/hooks/useSession.ts`、`useTypes.ts`、`useIdleLock.ts`
- Create: `frontend/src/components/AppLayout.tsx`
- Create: `frontend/src/pages/LockPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 会话 hook**

`useSession.ts`：

```ts
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { SessionStatus } from "../types";

export function useSession() {
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.session.status());
      setError("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法连接后端");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const run = async (action: () => Promise<SessionStatus>) => {
    setBusy(true);
    setError("");
    try {
      setStatus(await action());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return {
    status,
    busy,
    error,
    refresh,
    setup: (password: string) => run(() => api.session.setup(password)),
    unlock: (password: string) => run(() => api.session.unlock(password)),
    lock: () => run(() => api.session.lock()),
  };
}
```

`useIdleLock.ts`：监听 `mousemove/keydown/click/scroll`，5 分钟无操作调用 `onIdle`（App 里调用 lock 并提示）。

- [ ] **Step 2: 锁屏页**

`LockPage` 根据 `status.initialized` 显示：
- 未初始化：标题“设置主密码”、密码 + 确认（≥8 位，两次一致）、说明“主密码不存储，遗失将无法解密历史数据”。
- 已初始化：解锁密码输入、错误提示、锁定原因（如自动锁定）。
- 按钮 loading，按 Enter 提交。

- [ ] **Step 3: 布局与导航**

`AppLayout`：AntD `Layout` + `Sider` + `Menu`，菜单项“文档脱敏 / 批量处理 / 类型库 / 设置”，点击切换页面（App 内 state，无路由）。Header 右侧显示 LLM 模式 Tag（online 绿色、ollama 蓝色、rules 橙色并提示“离线规则模式”）、“锁定”按钮。

`App.tsx`：
- `useSession()`；未解锁渲染 `LockPage`；已解锁渲染 `AppLayout` + 当前页面。
- `useTypes()` 在解锁后加载类型，提供 `code -> TypeDefinition` 映射。
- `useIdleLock(5 * 60 * 1000, lock)`。
- 全局 `message` 提示。

- [ ] **Step 4: 验收**

`npm run build` 通过；浏览器开发模式下未初始化时显示设置密码页，设置后可进入工作台，刷新后显示解锁页。

---

## Task 4: 文档工作台

**Files:**
- Create: `frontend/src/pages/WorkbenchPage.tsx`
- Create: `frontend/src/components/UploadPanel.tsx`、`DocumentList.tsx`、`DetectionTable.tsx`

- [ ] **Step 1: 页面结构**

工作台三栏：左侧文档列表（上传 + 列表），中间编辑区，右侧识别结果/脱敏配置。使用 AntD `Row/Col` 或 CSS Grid。

`UploadPanel`：`Upload.Dragger`，accept `.txt,.md,.log,.py,.java,.js,.ts,.json,.csv,.eml,.docx,.pdf,.doc`，单文件，调用 `api.documents.upload`，成功后刷新列表并选中。

`DocumentList`：显示名称、扩展名、状态 Tag、时间；点击选中；删除按钮暂不做（后端无删除接口）。

`WorkbenchPage` 状态：
- `documents`、`selectedId`、`detail`、`spans`、`maskResult`、`mode`、`loading`。
- 选中后 `api.documents.get(id)`。
- “识别”按钮：`detect(id, true)`，保存 spans、mode，刷新详情。
- 编辑区使用 `Input.TextArea`（monospace，autoSize 最小 420px），点击“保存修改”调用 `saveText`，之后状态变 uploaded，需重新识别。
- 顶部 StatBar：识别数、规则/LLM 来源计数、当前模式。

`DetectionTable`：
- 列：类型（用 types 映射中文名）、片段（截断 tooltip）、位置（start-end）、置信度（Progress 或百分比）、来源 Tag、等级 Tag。
- 默认按 `start` 排序，可按类型筛选。
- 提示“span 为字节/字符偏移，仅后端使用，前端展示原文片段”。

- [ ] **Step 2: 验收**

开发模式上传 txt，列表出现文档，点击后能看到原文；点识别后表格出现手机号/身份证等条目。

---

## Task 5: 脱敏配置、对比与导出

**Files:**
- Create: `frontend/src/components/MaskPanel.tsx`、`CompareView.tsx`、`ExportBar.tsx`
- Modify: `WorkbenchPage.tsx`

- [ ] **Step 1: MaskPanel**

- 对当前识别结果中出现的每个 `type_code` 生成一行：
  - 类型名称、当前默认动作；
  - `Select`：屏蔽/替换/模糊化/加密；
  - 若为屏蔽：`keepPrefix` / `keepSuffix` 数字输入（默认取类型配置）；
- “执行脱敏”按钮：组装 `actions`，调用 `api.documents.mask(id, actions, true)`；展示 `verify.passed`、issues、stats；失败时红色 Alert。
- 脱敏成功后自动加载 compare。

- [ ] **Step 2: CompareView**

并排两栏：
- 原文：按 `spans` 用 `<mark className={`hit-${level}`}>` 包裹，点击 mark 弹出类型/置信度/来源。
- 脱敏文：直接展示 `masked`，并对 `applied` 中的 replacement 用浅色 mark 标出（从 mask 响应保存 applied）。
- 顶部说明“高亮颜色对应敏感等级；脱敏文为服务端返回结果”。
- 实现 `renderHighlighted(text, spans)` 返回 React 节点数组，避免 `dangerouslySetInnerHTML`。

- [ ] **Step 3: ExportBar**

按钮：
- “导出脱敏文件”（调用 download kind=masked fmt=auto，保存文件名 `${原名}_masked.${ext}`）；
- “导出报告 JSON”“导出报告 PDF”：点击弹出 `Modal` 输入主密码，调用 download kind=report，保存 `报告.json/pdf`；
- 导出失败用 `message.error` 展示 detail（401/403/409 文案对应“需要主密码”“密码错误”“尚未完成有效脱敏”）。

- [ ] **Step 4: 验收**

上传含手机号/身份证的 txt → 识别 → 执行脱敏 → 对比两栏无原文手机号 → 导出 txt 无原文 → 导出报告需输入主密码。

---

## Task 6: 批量处理页

**Files:**
- Create: `frontend/src/pages/BatchPage.tsx`

- [ ] **Step 1: 实现**

- 多文件 `Upload.Dragger`（`multiple`）。
- “开始批量处理”：调用 `api.batches.create(files)`，保存 batchId。
- 每 1.5 秒轮询 `api.batches.get(id)`，直到 `status === "done"`；用 `Progress` 显示 `done/total`。
- 表格列：序号、状态 Tag、消息、文档 ID（短）、操作“在工作台打开”（回调 `onOpenDoc(docId)`）。
- 批量结束后提示“已完成，可逐个打开文档导出脱敏文件与报告”。
- 页面说明“批量任务在后台串行/双并发处理，关闭页面不影响后端执行”。

- [ ] **Step 2: 验收**

一次上传 3 个 txt，进度到 100%，全部 status done，点击“打开”能跳到工作台并选中对应文档。

---

## Task 7: 类型库页

**Files:**
- Create: `frontend/src/pages/TypesPage.tsx`

- [ ] **Step 1: 实现**

- `Table` 列：代码、名称、类别、等级、默认动作、来源（内置/自定义）、操作（编辑/删除）。
- 内置类型只读（编辑按钮禁用，提示“内置类型不可覆盖，可新建自定义类型”）。
- “新建类型”Modal 字段：
  - code（大写字母/下划线）、name、category、level、defaultAction；
  - 识别方式：正则（pattern，可选忽略大小写）、关键词（逗号分隔）、是否交给大模型（hint）；
  - 保存时组装 `detectors`，调用 `api.types.save`；
  - 保存失败展示 detail（如“正则表达式无效”）。
- “样例测试”Modal：多行样例，调用 `api.types.test`，展示每条命中的片段与位置。
- 删除自定义类型需 `Popconfirm`。

- [ ] **Step 2: 验收**

新建 `EMP_NO` 正则 `EMP-\d{4}`，保存成功；样例测试 `EMP-1234` 命中；删除后列表消失；尝试修改内置手机号类型时按钮禁用。

---

## Task 8: 设置页

**Files:**
- Create: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: 实现**

- 读取 `api.settings.getLlm()` 初始化表单。
- 模式 `Select`：在线 API / 本地 Ollama / 纯规则。
- 在线：Base URL、模型名、API Key（`Input.Password`，占位“已保存，留空则不修改”，旁边 `has_key` 标记）。
- Ollama：地址、模型名。
- “保存配置”调用 `putLlm`；“测试连接”调用 `testLlm`，展示 `ok/mode/latency_ms/items` 或错误信息。
- 说明：在线模式会先对身份证/手机号等做本地遮蔽再上云；纯规则模式不联网。
- 保存后刷新会话状态（LLM 模式 Tag 更新）。

- [ ] **Step 2: 验收**

保存在线配置后 `has_key` 为真且页面不回显 Key；纯规则模式测试返回 `ok=false` 并提示“未配置在线或本地模型”。

---

## Task 9: Electron 主进程与预加载

**Files:**
- Create: `electron/main.cjs`、`electron/preload.cjs`
- Modify: `frontend/package.json`（`main` 指向 `../electron/main.cjs`，增加 dev 脚本）

- [ ] **Step 1: `preload.cjs`**

```js
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("privacyDesk", {
  apiBase: process.env.PRIVACY_DESK_API_BASE || "http://127.0.0.1:8765",
  token: process.env.PRIVACY_DESK_APP_TOKEN || "",
});
```

- [ ] **Step 2: `main.cjs`**

职责：
1. 选择随机空闲端口（`net.createServer().listen(0)` 获取 port 后关闭）。
2. 生成 32 字节令牌（`crypto.randomBytes(32).toString("hex")`）。
3. 启动后端：
   - 开发：`process.env.PRIVACY_DESK_BACKEND_CMD` 或默认 `py -3.12 run.py`，cwd 为 `privacy-desk/backend`；
   - 打包：`path.join(process.resourcesPath, "backend", "privacy-backend.exe")`。
   - 环境变量：`APP_TOKEN`、`PRIVACY_DESK_PORT`、`PRIVACY_DESK_APP_TOKEN`、`PRIVACY_DESK_API_BASE`、`PRIVACY_DESK_ENFORCE_INTEGRITY=1`（仅打包）、`PRIVACY_DESK_REQUIRE_ENCRYPTED_RESOURCES=1`、`PRIVACY_DESK_REQUIRE_TOKEN=1`。
4. 轮询 `GET /api/v1/health`（带 `X-App-Token`）最多 40 秒；失败 `dialog.showErrorBox("后端启动失败", stderr)` 并退出。
5. 创建 `BrowserWindow`：`webPreferences: { preload, contextIsolation: true, nodeIntegration: false, sandbox: true }`；`show: false`，`ready-to-show` 后显示。
6. 加载：
   - `PRIVACY_DESK_DEV_URL`（默认 `http://localhost:5173`）存在时 `loadURL`；
   - 否则 `loadFile(path.join(__dirname, "..", "frontend", "dist", "index.html"))`；打包后为 `path.join(process.resourcesPath, "ui", "index.html")`。
7. 安全：`setWindowOpenHandler` 一律 `deny`；`will-navigate` 非本地地址阻止；`app.on("window-all-closed")` 退出；退出前 `child.kill()`。

- [ ] **Step 3: 验收**

`cd frontend && npm run electron:dev` 能启动窗口；关闭窗口后 Python 进程被终止。

---

## Task 10: 打包脚本与使用说明

**Files:**
- Create: `backend/build/pyinstaller.spec`
- Create: `electron-builder.yml`
- Create: `scripts/build.ps1`
- Create: `README.md`（项目根，使用说明）

- [ ] **Step 1: PyInstaller spec**

入口 `backend/run.py`，`datas` 只包含 `resources/rules.enc`（不要打包 `types.default.json` 与 `prompts/*.txt`），`console=False`，`name="privacy-backend"`，输出 `backend/dist/privacy-backend/`。

构建顺序：
1. `cd backend && .venv\Scripts\python.exe build\encrypt_resources.py`
2. `.venv\Scripts\pyinstaller.exe build\pyinstaller.spec --noconfirm`
3. `.venv\Scripts\python.exe build\encrypt_resources.py dist\privacy-backend`（复制加密资源并生成 manifest）
4. 检查 `dist\privacy-backend\manifest.json` 存在。

- [ ] **Step 2: electron-builder.yml**

```yaml
appId: com.privacy.desktop
productName: 隐盾 PrivacyDesk
directories:
  output: release
files:
  - frontend/dist/**
  - electron/**
  - package.json
extraResources:
  - from: backend/dist/privacy-backend
    to: backend
  - from: frontend/dist
    to: ui
win:
  target:
    - nsis
nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
```

（`package.json` 放在 `privacy-desk/` 根，`main` 指向 `electron/main.cjs`；electron-builder 从根目录运行。）

- [ ] **Step 3: `scripts/build.ps1`**

按顺序：前端 `npm ci` + `npm run build` → 后端加密资源 + PyInstaller + manifest → `npx electron-builder --win --x64` → 输出 `release/`。任一步失败即 `exit 1`。

- [ ] **Step 4: `README.md`**

包含：系统简介、功能、安装包使用、首次设置主密码、LLM 配置（DeepSeek/OpenAI 兼容/Ollama）、支持格式与限制（.doc 需 LibreOffice、PDF 重建版、docx 文本框/超链接目标不覆盖）、数据位置与卸载清理（`%USERPROFILE%\.privacy-desk`）、开发运行命令、构建命令、完整性校验说明、目录结构。

- [ ] **Step 5: 验收**

`scripts/build.ps1` 产出 `release/*.exe`；安装后首次启动能设置主密码；断网时以 rules 模式可用；篡改 `backend/resources/rules.enc` 后启动失败并给出完整性/资源错误。

---

## 自检结果

- 规格覆盖：主密码门禁（Task 3）、文档工作台/在线编辑（Task 4）、识别结果与类型标注（Task 4/7）、四种脱敏配置（Task 5）、前后对比（Task 5）、批量（Task 6）、自定义类型（Task 7）、LLM 设置与降级展示（Task 8）、加密存储与完整性（后端已实现，Task 9/10 接线）、安装包与使用说明（Task 10）。
- 已知取舍：批量导出采用逐个文档导出，不做后端 zip；自动锁定在前端 5 分钟空闲触发（后端不强制）；PDF 导出为重建版；docx 文本框/超链接目标不在脱敏范围。
