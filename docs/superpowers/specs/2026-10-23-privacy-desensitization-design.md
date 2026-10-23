# 基于大模型的文本隐私信息智能脱敏系统 — 设计文档

- 日期：2026-10-23
- 状态：已确认
- 对应题目：课程设计题目 73

## 1. 目标与背景

构建一款本地运行的桌面应用，对文档、邮件、聊天记录、代码注释等文本中的隐私信息进行语义识别与脱敏，并保证原文与脱敏结果加密存储、核心规则受保护、软件可校验完整性。

系统面向单机单用户场景，交付完整安装包与使用说明。

## 2. 范围

### 2.1 包含

- 多格式文本导入：txt、md、docx、pdf、doc（依赖 LibreOffice）、常见代码与日志文本
- 隐私类型体系：内置 10 类 + 用户自定义类型，支持样例校验
- 双引擎识别：规则引擎（正则、校验位、Luhn、词典）+ 大模型语义识别
- 在线 LLM 与本地 Ollama 双通道，失败自动降级为规则模式
- 四种脱敏方式：替换、加密、屏蔽、模糊化，按类型配置
- 脱敏效果校验：复扫残留、格式合规、可读性指标
- 单文档与批量处理、在线编辑、前后对比、报告导出
- 主密码解锁、字段级 AES-256-GCM 加密、自动锁定、审计日志
- 算法与规则资源加密、启动完整性校验
- Electron 安装包（内嵌 PyInstaller 冻结的 FastAPI sidecar）

### 2.2 不包含

- 多用户、角色权限、服务端部署
- PDF 原版式保留（导出为重建版 PDF，界面明示）
- 全量可逆还原（仅"加密"型脱敏的 token 可由主密钥解开）
- 云端同步、协作、移动端

## 3. 总体架构

```
Electron 主进程
 ├─ 启动并守护 FastAPI sidecar（随机端口 + 一次性启动令牌）
 ├─ 完整性校验（manifest + HMAC）
 └─ BrowserWindow（contextIsolation=true、CSP、禁用 nodeIntegration）

渲染进程：React 18 + TypeScript + Vite + Ant Design + Monaco Editor

FastAPI 后端
 ├─ api/        路由与请求校验
 ├─ core/ingest  文档解析与写回
 ├─ core/detect  规则引擎、LLM 引擎、融合
 ├─ core/mask    脱敏算子、一致性映射、校验器
 ├─ core/report  报告生成
 ├─ core/store   SQLite + 字段级加密仓储
 ├─ core/security 密钥派生、加密资源、完整性
 └─ llm/         OpenAI 兼容客户端、Ollama 客户端、分块与缓存
```

### 3.1 进程与通信

1. Electron 主进程挑选空闲端口，生成 32 字节启动令牌，以环境变量传给 sidecar。
2. sidecar 仅监听 `127.0.0.1`，所有 `/api/*` 请求需携带 `X-App-Token`。
3. 前端开发模式经 Vite 代理访问，生产模式由 FastAPI 托管静态资源。
4. Electron 通过 `child_process.spawn` 管理 sidecar，退出时终止。

## 4. 数据模型

### 4.1 SQLite 表

| 表 | 关键字段 | 说明 |
|---|---|---|
| `app_meta` | key TEXT PK, value BLOB | 盐值、KDF 参数、canary、schema 版本 |
| `documents` | id TEXT PK, name BLOB, ext, size, sha256, status, created_at, updated_at | 文件名加密，状态为 uploaded/detected/masked/verified/failed |
| `doc_versions` | id, doc_id, kind(original/edited/masked), content BLOB, nonce BLOB, created_at | 正文密文，AAD 绑定 id |
| `detections` | id, doc_id, version_id, type_code, category, start, end, text BLOB, confidence, source(rule/llm), level, action | span 明细，text 加密 |
| `mask_jobs` | id, doc_id, config BLOB, status, stats BLOB, created_at | 一次脱敏任务 |
| `reports` | id, doc_id, job_id, format, content BLOB, nonce BLOB, created_at | JSON/PDF 报告密文 |
| `custom_types` | code TEXT PK, config BLOB | 自定义与内置类型配置 |
| `app_settings` | key TEXT PK, value BLOB | LLM 配置、默认脱敏策略 |
| `batch_jobs` | id, status, total, done, created_at | 批量任务 |
| `batch_items` | id, batch_id, doc_id, status, message | 批量明细 |
| `audit_logs` | id, action, detail TEXT, created_at | 不含明文 |

### 4.2 类型定义

```json
{
  "code": "ID_CARD_CN",
  "name": "身份证号",
  "category": "personal_id",
  "level": "high",
  "builtin": true,
  "enabled": true,
  "detectors": [
    {"kind": "regex", "pattern": "(?<!\\d)\\d{17}[\\dXx](?!\\d)"},
    {"kind": "checksum", "algo": "gb11643"},
    {"kind": "llm", "hint": "识别中国大陆居民身份证号"}
  ],
  "defaultAction": "mask",
  "actionOptions": {"keepPrefix": 0, "keepSuffix": 4}
}
```

- `detectors[].kind` 取值：`regex`、`checksum`（gb11643/luhn）、`keyword`、`dict`、`llm`。
- 内置类型：身份证、手机号、银行卡、姓名、地址、邮箱、IP、车牌、护照、涉密关键词。
- 自定义类型保存前执行样例校验：至少一条命中、至少一条反例不命中。

### 4.3 Span 模型

```json
{
  "start": 152,
  "end": 170,
  "typeCode": "PHONE_CN",
  "text": "13800138000",
  "confidence": 0.98,
  "source": "rule"
}
```

坐标为文档统一模型中的字符偏移；所有引擎输出必须归一到该模型。

## 5. 识别流水线

### 5.1 文档解析

- 统一模型：`Document { blocks: [Paragraph | TableCell | CodeBlock], text: string, offsetMap }`
- txt/md/log/代码：探测 UTF-8/GBK，按行分块，代码注释整体作为可扫描文本。
- docx：python-docx 遍历段落、表格、页眉页脚；写回时合并跨 run 的实体再替换。
- pdf：pdfplumber 提取文本；导出使用 reportlab 重建，内置中文字体。
- doc：调用 `soffice --headless --convert-to docx`，缺失时返回可读错误。

### 5.2 分块

- 每块 ≤ 2000 字符，相邻块重叠 100 字符。
- 实体可能跨块，融合阶段对相邻块的重叠区域做去重与合并。

### 5.3 规则引擎

- 正则 + 校验位（GB 11643 加权模 11-2）+ Luhn + 号段与长度约束。
- 词典匹配：常见姓氏库用于姓名候选，涉密关键词库可导入。
- 大小写、全角半角归一化后匹配，回填原始偏移。

### 5.4 本地预遮蔽（云端隐私保护）

调用在线 LLM 前，先对规则引擎命中的高敏 span 做**等长**遮蔽（逐字符替换为 `█`）。等长保证 LLM 返回片段仍可与原文偏移一一对应，云端看不到身份证号、银行卡号、手机号原文。

### 5.5 LLM 引擎

- 请求：系统提示词约束只输出 JSON 数组 `[{type, text, confidence, reason}]`；`temperature=0`；超时 30s；重试 2 次。
- 定位：以返回的 `text` 在原文中检索，不采用模型给出的偏移；同一片段多处出现时全部标记，随后由用户按位置取舍。
- 结果缓存：键为 `sha256(分块文本 + 类型版本 + 模型名)`。
- 降级链：在线失败 → 本地 Ollama（已配置时）→ 纯规则模式，界面顶部显示当前模式。

### 5.6 融合

- 格式强校验类（身份证、银行卡、手机号、邮箱、IP、车牌、护照）：规则结果优先，LLM 结果仅补充规则未覆盖的位置。
- 语义类（姓名、地址、涉密信息）：LLM 结果优先，规则词典作为补充。
- 重叠处理：同类取更长 span；跨类取 `level` 更高者；融合后按 `(start, end, typeCode)` 去重。

## 6. 脱敏流水线

### 6.1 算子

| 方式 | 行为 | 示例 |
|---|---|---|
| 屏蔽 mask | 保留前后 N 位，中间等长替换 | 138****8000 |
| 替换 replace | 类型占位符或假名 | [手机号_1]、张*三 |
| 模糊化 fuzz | 按类型泛化 | 北京市朝阳区某路 → 某市某区 |
| 加密 encrypt | AES-256-GCM(docId+序号) 加密实体，输出 `ENC:base64url`，可由主密钥解开 | ENC:9f3a... |

- 默认策略：身份证/银行卡/手机号 = 屏蔽；姓名 = 替换；地址 = 模糊化；涉密信息 = 加密。
- 用户可在本次任务中按类型覆盖。

### 6.2 一致性映射

同一 `(typeCode, 规范化文本)` 在单次任务内映射到同一 token（如 `[姓名_1]`），保证全文指代一致、可读。映射表仅存于任务内存，任务结束丢弃，不落盘。

### 6.3 校验器

1. 对脱敏结果重跑规则引擎，命中数必须为 0（高敏类型）或低于阈值。
2. 格式合规：脱敏结果不得再次匹配原类型正则（如 18 位仍成立则失败）。
3. 可读性：长度变化率 > 40% 或占位符密度 > 15% 时给出警告。
4. 任一失败项标红，允许"一键补脱敏"后重新校验。

## 7. 交互与功能

- **文档工作台**：上传（拖拽/选择）、文档列表、状态标签、识别按钮。
- **结果面板**：按类型分组，展示位置、片段、置信度、来源；支持单条启用/忽略。
- **在线编辑**：Monaco 编辑原文，保存为新版本后可重跑识别。
- **脱敏配置**：按类型选择脱敏方式与参数，实时预览首条效果。
- **对比视图**：左右同步滚动、按类型着色、点击互相定位；顶部统计识别数/脱敏数/残留数/耗时。
- **批量**：并发 2，进度与失败原因可见，结果打包 zip（脱敏文件 + 汇总报告）。
- **导出**：脱敏文件（按原格式）+ JSON 全量报告 + PDF 汇总报告；敏感导出需再次输入主密码。
- **设置**：LLM 服务地址、模型名、API Key（加密存储）、Ollama 地址、降级开关、类型管理。

## 8. 安全设计

### 8.1 密钥体系

- 首次启动设置主密码（≥8 位，强度提示）；随机 16B 盐存 `app_meta`。
- `MK = Argon2id(password, salt, m=64MiB, t=3, p=2)`，32 字节，仅驻留内存。
- canary：AES-256-GCM(MK, 固定串) 存库，能解密即密码正确。
- `DK = HKDF-SHA256(MK, "data/v1")` 用于业务数据加密。

### 8.2 加密存储

- 所有正文、识别片段、报告、配置均以 AES-256-GCM 加密，随机 12B nonce，AAD 绑定记录 id。
- 数据库只保留不可逆索引（文档 sha256、时间、状态）用于检索。
- 自动锁定：5 分钟无操作清空 MK；连续 5 次密码错误后指数退避。

### 8.3 核心算法保护

- 规则库、提示词模板、算子参数构建时整体加密为 `rules.enc`。
- 运行时解密密钥由内置种子与应用版本派生，直接拷贝资源文件无法使用。

### 8.4 完整性校验

- 构建脚本生成 `manifest.json`（每个文件 SHA-256）并用内置密钥 HMAC-SHA256 签名。
- 启动时 Electron 校验 sidecar 与前端资源，后端校验加密资源；失败则拒绝启动并提示重装。
- 安装包使用自签名证书签名（演示环境说明信任方式）。

### 8.5 攻击面收敛

- 后端仅绑定 127.0.0.1、随机端口、启动令牌校验。
- Electron 开启 contextIsolation、sandbox、CSP，禁用远程模块与外部导航。
- 上传限制单文件 20MB，类型白名单；解析失败不执行任何外部命令（doc 转换除外，参数固定）。
- 审计日志只记录动作、类型、数量、耗时。

## 9. API 设计

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/session/setup` | 首次设置主密码 |
| POST | `/api/v1/session/unlock` | 解锁，返回会话状态 |
| POST | `/api/v1/session/lock` | 锁定并清空密钥 |
| GET | `/api/v1/session/status` | 是否已初始化/已解锁 |
| POST | `/api/v1/documents` | 上传并解析文档 |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/documents/{id}` | 文档详情与版本 |
| PUT | `/api/v1/documents/{id}/content` | 在线编辑保存 |
| POST | `/api/v1/documents/{id}/detect` | 执行识别，返回 span |
| POST | `/api/v1/documents/{id}/mask` | 执行脱敏与校验 |
| POST | `/api/v1/documents/{id}/verify` | 重新校验 |
| GET | `/api/v1/documents/{id}/compare` | 前后对比数据 |
| GET | `/api/v1/documents/{id}/export` | 导出脱敏文件/报告 |
| POST | `/api/v1/batches` | 创建批量任务 |
| GET | `/api/v1/batches/{id}` | 批量进度与明细 |
| GET/PUT | `/api/v1/types` | 类型列表/保存自定义类型 |
| POST | `/api/v1/types/test` | 样例校验 |
| GET/PUT | `/api/v1/settings/llm` | LLM 配置 |
| POST | `/api/v1/settings/llm/test` | 连通性测试 |

## 10. 错误处理与降级

- LLM 超时/限流：重试后降级，任务标记 `degraded`，界面提示当前模式。
- 单文件解析失败：批量任务继续，记录原因。
- 主密码错误：明确提示并计数，达阈值退避。
- 校验未通过：文档状态保持 `detected`，不允许标记完成，需补脱敏。
- 加密资源校验失败：后端拒绝启动，Electron 弹出完整性告警。

## 11. 测试策略与验收

- 单元测试：校验位、Luhn、分块去重、span 融合、偏移映射、四种算子、加解密往返、密码错误路径。
- 集成测试：四类格式上传 → 识别 → 脱敏 → 校验 → 导出全链路。
- 语料：内置 120 条标注样例，覆盖 10 类隐私与 4 类脱敏方式。
- 验收指标：规则类召回 ≥ 95%、精确率 ≥ 98%；在线 LLM 语义类召回 ≥ 85%；高敏类型脱敏残留为 0；加解密往返一致。

## 12. 打包与分发

- 后端：PyInstaller 单目录模式冻结，排除测试依赖。
- 前端：Vite 构建后由 FastAPI 托管，Electron 仅作壳。
- 构建脚本顺序：加密资源 → 生成 manifest → 前端构建 → 后端冻结 → electron-builder 出包。
- 交付物：安装包、使用说明（安装、首次设密码、LLM 配置、格式限制、卸载与数据清理）。

## 13. 已知限制

- 旧版 .doc 需本机安装 LibreOffice。
- PDF 导出为重建版，复杂版式不保留。
- 离线模式仅规则可用（或需本地 Ollama）。
- 安装包体积较大（Electron + Python 运行时）。

## 14. 实施里程碑

1. M0 工程骨架：目录、依赖、Electron 壳与 FastAPI 健康检查
2. M1 安全基础：密钥派生、会话解锁、加密仓储、完整性校验骨架
3. M2 文档解析：txt/md/docx/pdf/doc 与统一模型、偏移映射
4. M3 规则识别：类型配置、校验位/Luhn、融合与结果面板数据
5. M4 LLM 接入：分块、提示词、预遮蔽、降级链、缓存
6. M5 脱敏与校验：四种算子、一致性映射、复扫
7. M6 前端工作台：上传、识别、配置、对比、导出
8. M7 批量与报告：队列、zip 导出、PDF/JSON 报告
9. M8 安全加固：资源加密、manifest、Electron 加固
10. M9 打包与文档：PyInstaller、electron-builder、使用说明
