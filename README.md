# 隐盾 PrivacyDesk 使用说明

隐盾 PrivacyDesk 是一款**完全本地运行**的文档隐私脱敏桌面应用。后端为本地 FastAPI 服务，前端为 React + Ant Design 界面，由 Electron 外壳以随机端口 + 一次性令牌拉起后端，所有业务数据保存在本机，不上传云端（启用在线大模型时除外，且会先做本地高敏遮蔽）。

## 一、功能清单

- **主密码门禁**：首次启动设置主密码，之后每次启动解锁；登录后可随时手动锁定。
- **文档工作台**：上传文档后自动识别敏感信息（规则 + 大模型），按类型配置脱敏方式，执行脱敏并自动校验，原文/脱敏文并排对比。
- **四种脱敏方式**：屏蔽（可保留前/后缀）、替换（假名化）、模糊化、加密（可逆，需主密码）。
- **导出**：导出脱敏文件；导出 JSON / PDF 脱敏报告（报告导出需再次输入主密码）。
- **批量处理**：一次上传多份文档，后台串行处理并生成脱敏结果，完成后逐个打开导出。
- **类型库**：内置手机号、身份证等类型只读；可新建自定义正则 / 关键词 / 大模型提示类型，并做样例测试。
- **大模型设置**：在线 API（DeepSeek / OpenAI 兼容）、本地 Ollama、纯规则三种模式；在线模式失败时自动降级到 Ollama 或纯规则。

## 二、安装与首次使用

1. 双击安装包 `隐盾 PrivacyDesk Setup x.y.z.exe`，按向导选择安装目录（支持自定义路径），完成后桌面会生成快捷方式。
2. 首次启动会进入“设置主密码”页面：密码至少 8 位，需要输入两次确认。
   - **主密码不存储在任何地方**，仅用于派生加密密钥。遗忘后历史加密数据无法恢复，请妥善保管。
3. 设置完成后进入工作台。此后每次启动都需要输入主密码解锁。
4. 顶部工具栏可随时点击“锁定”。

## 三、文档处理流程

1. **上传**：在工作台左侧拖入或点击选择文件（单个文件）。
2. **自动识别**：上传完成后或打开尚未识别的文档时，系统自动先用规则引擎匹配，再按当前 LLM 模式调用大模型补充；识别结果作为主区域，按类型、片段、位置、置信度、来源（规则/大模型）、敏感等级展示。
3. **进入脱敏配置**：识别结果下方的「执行脱敏」按钮会进入脱敏配置页，为出现的每种类型选择屏蔽 / 替换 / 模糊化 / 加密；屏蔽方式可设置保留前 N 位、后 N 位。
4. **执行脱敏**：在脱敏配置底部点击「执行脱敏」，后端返回脱敏文本、统计信息与自动校验结果，主区域随即切换为原文/脱敏文对比。校验不通过会提示残留项与问题列表。
5. **对比**：原文与脱敏文并排展示，原文中的命中片段按敏感等级着色，点击可查看类型、置信度与来源。
6. **导出**：导出脱敏文件（保持原扩展名）；或导出 JSON / PDF 报告，导出报告时需再次输入主密码。

## 四、大模型配置

进入“设置”页选择模式：

| 模式 | 说明 |
| --- | --- |
| 在线 API | 填写 Base URL、模型名、API Key。默认 `https://api.deepseek.com/v1` + `deepseek-chat`，也可填入任意 OpenAI 兼容服务地址。 |
| 本地 Ollama | 填写 Ollama 地址（默认 `http://127.0.0.1:11434`）与模型名（默认 `qwen2.5:7b`）。 |
| 纯规则 | 不联网，仅使用内置正则 / 校验位 / 关键词规则，适合完全离线的场景。 |

- API Key 加密保存，页面不回显；留空提交表示不修改已保存的 Key。
- 支持从环境变量自动读取 Key：默认依次检测 `PRIVACY_DESK_LLM_KEY`、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`，设置页可追加自定义变量名。已保存的 Key 优先，环境变量仅作回退，且不会写入数据库；删除变量后即失效（用 `setx` 设置后需重启应用）。
- **云端前本地预遮蔽**：在线模式下，身份证号、手机号等高敏命中片段会先在本地替换为等长 `█` 再发送给云端，模型只负责补充识别其余类型；返回的片段仍可映射回原文位置。
- 在线调用失败会自动尝试 Ollama，仍失败则降级为纯规则模式，界面顶部 Tag 会显示当前实际模式。
- 纯规则模式下点击“测试连接”会提示“未配置在线或本地模型”。
- 切换到“本地 Ollama”模式时，设置页会自动检测填写的地址是否可连，并列出已拉取的模型；也可点“重新检测”。本机未安装 Ollama 不影响纯规则模式使用。

## 五、支持格式与限制

**支持导入**：`txt`、`md`、`log`、`py`、`java`、`js`、`ts`、`json`、`csv`、`eml`、`docx`、`pdf`、`doc`。
**单文件大小上限**：20 MB。

已知限制：

- `.doc` 需要本机安装 **LibreOffice**（提供 `soffice` 命令）先转换为 `.docx`，否则会提示“未检测到 LibreOffice”。
- **PDF 导出为重建版**：按脱敏后的纯文本重新排版生成 A4 PDF，不保留原 PDF 的版式、图片与表格结构。
- **docx 导出**保留段落样式与首个 run 的格式；正文、表格与页眉页脚会被扫描和写回，但**文本框内容、超链接目标地址、脚注/尾注/批注**不在脱敏范围内。
- 批量任务只负责识别与生成脱敏结果，**导出需要逐个文档进行**，不提供 zip 打包。
- 大模型识别结果依赖模型能力，可能存在漏检或误检，请结合校验结果与对比视图人工复核。

## 六、数据位置与卸载清理

- 业务数据保存在：`%USERPROFILE%\.privacy-desk`
  - `privacy.db`：SQLite 数据库，文档原文、脱敏结果、识别记录、报告、类型与设置均以 AES-256-GCM 密文存储。
- 卸载应用**不会自动删除**该目录。如需彻底清除，请在退出应用后手动删除 `%USERPROFILE%\.privacy-desk`。
- 由于主密码不落盘，删除数据目录后无法恢复任何历史文档。

## 七、开发运行

环境要求：Windows 10/11、Python 3.12、Node.js 18+。

```powershell
# 1) 后端依赖（首次）
cd backend
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2) 启动后端（默认 127.0.0.1:8765，无令牌）
.venv\Scripts\python.exe run.py

# 3) 启动前端开发服务器
cd ..\frontend
npm install
npm run dev

# 4) 根目录启动 Electron（同时拉起前端与后端）
cd ..
npm install
npm run dev
```

说明：

- `npm run dev` 会并行启动 Vite（`http://localhost:5173`）与 Electron；Electron 自动挑选空闲端口、生成一次性令牌并拉起后端。
- 仅调试界面时，可只跑 `npm run dev:ui`，浏览器访问 5173，此时前端回退到 `http://127.0.0.1:8765` 且不带令牌，需先单独启动后端。
- Electron 在非打包模式下优先使用 `backend\.venv\Scripts\python.exe run.py`；若虚拟环境不存在则尝试 `py -3.12 run.py`。

## 八、构建安装包

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
# 如使用 PowerShell 5.1 遇到中文脚本解析问题，改用 PowerShell 7：
# pwsh -ExecutionPolicy Bypass -File scripts\build.ps1
```

脚本按顺序执行：前端依赖安装 → 前端构建 → 后端全量测试 → 生成加密资源 → PyInstaller 打包后端 → 为冻结产物生成完整性清单 → 校验清单 → 根目录 Electron 依赖安装 → electron-builder 生成 NSIS 安装包。任一步失败即退出并返回非零码。

产物位于 `release\`：

- `隐盾 PrivacyDesk Setup x.y.z.exe`：NSIS 安装包（可选择安装目录、创建桌面快捷方式）。
- `win-unpacked\`：免安装运行目录，可直接运行 `隐盾 PrivacyDesk.exe`。

> 首次构建需要联网下载 Electron 与 Python 依赖。若 Electron 下载缓慢，可设置镜像：
> `set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`
>
> 若在非管理员账户下构建报 `winCodeSign` 符号链接错误，可开启 Windows 开发者模式或以管理员身份运行；
> 也可以临时跳过 EXE 签名与元数据编辑（安装包将使用 Electron 默认图标）：
> `npx electron-builder --win --x64 --config.win.signAndEditExecutable=false`

## 九、安全设计摘要

- **主密码 → 密钥**：Argon2id 派生主密钥，主密钥仅驻留内存，锁定即丢弃；数据密钥由主密钥二次派生。
- **数据加密**：所有文档内容、识别片段、报告与设置使用 AES-256-GCM 加密，绑定文档 ID 作为附加认证数据。
- **加密资源**：内置类型规则与提示词打包为 `rules.enc`，安装包中不包含明文 `types.default.json` 与 prompts。
- **完整性校验**：构建时对冻结产物生成 HMAC-SHA256 签名的 `manifest.json`，打包版启动时强制校验，文件被篡改或缺失会拒绝启动。
- **本地回环 + 令牌**：后端只监听 `127.0.0.1` 的随机端口；每次启动生成 32 字节随机令牌，所有 `/api/*` 请求必须携带 `X-App-Token`。
- **Electron 加固**：`contextIsolation: true`、`nodeIntegration: false`，预加载脚本仅暴露 `{ apiBase, token }`；禁止 `window.open`，导航仅允许开发地址与打包后的 `ui/index.html`；保留 `webSecurity` 默认值。

## 十、已知限制与故障排查

| 现象 | 可能原因与处理 |
| --- | --- |
| 启动时弹窗“后端启动失败” | 查看弹窗中的后端日志尾部。常见原因：端口被占用、缺少 VC++ 运行库、安装目录被杀毒软件隔离、打包产物缺少 `_internal` 目录。可尝试重装到其他目录或以管理员身份运行。 |
| “完整性校验失败”或“缺少完整性清单” | 安装目录中的后端文件被修改、杀毒软件篡改或复制不完整。请重新安装；不要手动改动 `resources\backend` 下的文件。 |
| 大模型识别无结果 / 顶部显示“纯规则” | API Key 未保存、Base URL 不可达、网络受限或 Ollama 未启动。到“设置”页点击“测试连接”确认；离线场景可直接使用纯规则模式。 |
| 导出报告提示“需要主密码”/“密码错误” | 报告导出要求二次输入当前主密码，连续输错会被拒绝，请确认大小写与输入法。 |
| 上传 `.doc` 报“未检测到 LibreOffice” | 安装 LibreOffice 并确保 `soffice` 在 PATH 中，或先手动另存为 `.docx` 再上传。 |
| 忘记主密码 | 无法找回。只能删除 `%USERPROFILE%\.privacy-desk` 重新初始化，历史数据将全部丢失。 |

## 十一、目录结构

```
.
├─ frontend/              React + Vite 前端
├─ backend/               FastAPI 后端（run.py 为入口）
│  ├─ app/
│  ├─ resources/          rules.enc、types.default.json、prompts
│  └─ build/              pyinstaller.spec、encrypt_resources.py
├─ electron/              main.cjs、preload.cjs
├─ scripts/build.ps1      一键构建脚本
├─ electron-builder.yml   安装包配置
├─ package.json           Electron 根工程
└─ README.md              本文件
```
