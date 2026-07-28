# 功能安全文档生成器 v3.0

> ISO 26262 / ASPICE 文档自动生成工具 · FastAPI + 单页应用（SPA）

基于 C/C++ 代码，通过接入大语言模型（LLM），自动生成满足 ISO 26262 和 ASPICE 标准的功能安全文档。

后端采用 **FastAPI**，前端为 **Bootstrap 5 + 原生 JavaScript** 的单页应用，LLM 生成通过 **SSE（Server-Sent Events）** 逐 token 流式渲染。代码解析、Token 预估等重活按需触发并缓存，避免大工程上传时的界面卡顿。

## 支持的文档类型

| 缩写 | 全称 | 依赖前置文档 |
|------|------|------|
| SRS | 软件需求规格说明 | — |
| SAD | 软件架构设计 | — |
| FMEA | 失效模式与影响分析 | SRS + SAD |
| DFA | 相关失效分析（CCF / 级联 / 单点 / FFI） | SRS + SAD + FMEA |
| SDD | 软件详细设计 | — |
| TC-UNIT | 单元测试用例（含 FMEA 导出故障注入） | SRS + SAD + FMEA + DFA |
| TC-INTEGRATION | 集成测试用例（含 DFA 级联失效验证） | SRS + SAD + FMEA + DFA |

## 系统要求

- Windows 10 / 11
- Python ≥ 3.10（推荐 3.13，需勾选 *Add python.exe to PATH*）
- 现代浏览器（Chrome / Edge / Firefox）
- 前端依赖（Bootstrap / marked / highlight.js）经 CDN 引入，无需 npm/打包，但首屏加载需联网

## 快速开始

### 一键启动（推荐）

双击 `启动工具.bat`，脚本会自动完成全部环境准备：

1. **检测系统 Python**：自动识别 `python` / `py` 命令，校验版本 ≥ 3.10；未安装时给出下载指引
2. **创建虚拟环境**：首次运行自动在项目目录创建 `.venv`
3. **安装依赖**：自动安装 `requirements.txt` 中的依赖包；默认源失败时自动切换清华镜像源重试
4. **依赖自检**：每次启动前检查依赖完整性，缺失时自动补装
5. **启动服务**：自动选择可用端口（8000~8010）启动 Uvicorn，并自动打开浏览器

等待命令行显示：

```
Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

然后在浏览器打开 [http://localhost:8000](http://localhost:8000)。

> 首次启动需下载依赖包，约需 3~5 分钟；之后每次启动仅需数秒。
> 若 8000 端口被占用，程序会自动尝试 8001~8010 端口，并在命令行显示实际地址。

### 手动配置环境（可选）

如需自行管理 Python 环境：

```powershell
cd fusa_sw_doc_generate_tool
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd src
..\.venv\Scripts\python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

> 注意：Uvicorn 需在 `src` 目录下启动（业务模块以 `src` 为根导入）。

### 使用

#### 第一步：配置 LLM

1. 在左侧配置栏选择**模型提供商**（OpenAI / Anthropic / DeepSeek / 通义千问 等）
2. 输入 **API Key**（支持多个 Key 轮询提升并发）；Key 仅保存在后端内存中
3. 选择 **ASIL 等级**（QM → ASIL D），Temperature 会自动联动

#### 第二步：上传代码

在「工程总览」页面上传 C/C++ 代码，支持四种方式：

- **选择文件**：上传 `.c` / `.cpp` / `.h` / `.hpp` 文件
- **上传 ZIP**：批量上传（支持多层目录）
- **本地路径**：直接指定本地工程根目录路径
- **粘贴代码**：手动粘贴代码段

> ⚠️ **上传后**：系统自动解析代码并检测软件模块。模块列表会**自动加载**到「工程总览」和「单文档工作台」中；如未显示，**刷新浏览器页面**即可。

#### 第三步：预估 Token（可选）

切换到「单文档工作台」：

- **选择模块**：点击模块 Chip 切换查看不同模块的 Token 预估
  - **普通点击**：单选模块（其他自动取消选中），预估面板立即更新
  - **Ctrl + 点击**：多选模块（用于批量生成），预估标签显示 "N 个模块"
  - 点「全选」/「清空」按钮可快速操作全部模块
- **勾选选项**：「分段生成」和「审查修订」会影响预估结果
- 面板实时展示：源代码 Token、预计输出、合计和预计成本

#### 第四步：生成文档

- **单文档生成**：在「单文档工作台」选择 Agent + 模块，点击 **生成文档**（SSE 流式输出，逐 token 实时渲染，生成过程中可随时取消）
- **批量生成**：在「工程总览」勾选模块范围，点击 **一键批量生成**，按 模块 × Agent 顺序依次生成，支持断点续传与随时取消

#### 第五步：导出与查看

- **查看结果**：生成完成后自动显示在右侧面板，支持 Markdown 渲染预览
- **导出格式**：Markdown / Word（.docx）/ Excel（.xlsx，FMEA 专属）/ 全量打包 ZIP
- **历史恢复**：已生成文档持久化保存（`saved_results.json`），重启服务后自动恢复
- **再次生成**：在「工程总览」点击已生成文档即可重新生成或导出

## 核心特性

- **7 种文档类型**：SRS / SAD / FMEA / DFA / SDD / TC-UNIT / TC-INTEGRATION
- **多模型支持**：OpenAI / Anthropic / 通义千问 / DeepSeek / 智谱 GLM / Kimi / 自定义 API
- **SSE 流式生成**：逐 token 实时渲染，生成过程可见、可中断
- **免卡顿架构**：后端定向 API + 前端局部重渲染；代码解析/预估按需触发并按 hash 缓存
- **多 Key 轮询**：配置多个 API Key，分段并发时自动轮询提升并发上限
- **分段并发生成**：长文档拆段并发，多线程 token 经队列汇入单条 SSE 流
- **批量断点续传/取消**：批量生成支持逐模块逐 Agent 断点续传与随时取消
- **安全知识库注入**：内置失效模式库、安全机制 DC 表、ASIL 分解规则，降低 LLM 幻觉
- **前置文档自动注入**：FMEA/DFA/TC 自动注入 SRS/SAD 等前置文档提升一致性
- **跨文档追溯校验**：自动检查 SRS→FMEA→DFA→TC 的 ID 引用覆盖率
- **代码-文档一致性**：检测 LLM 虚构函数（幻觉），验证高复杂度函数的文档覆盖
- **分段一致性合并**：多段并发生成后自动执行术语/编号/交叉引用一致性审查
- **审查修订**：可选生成后自动审查修订，保留版本供 Diff 对比
- **Token 精准预估**：计入知识库、前置文档、多轮调用，误差 < 10%
- **质量校验**：内置 ISO 26262 / ASPICE 合规校验（ID 格式、RPN 范围、追溯性等）
- **AST 级代码解析**：基于 tree-sitter 精确提取函数、结构体、宏定义
- **自定义模板**：上传 .md / .txt / .rst / .docx / .xlsx 模板，按模板格式输出
- **多格式导出**：Markdown / Word（.docx）/ Excel（.xlsx，FMEA 专属）/ 全量打包 ZIP
- **生成历史与持久化**：自动记录生成配置与结果，重启后恢复已生成文档

## 配置方式

### 手动填写

在左侧配置栏逐项填写提供商、API Key、模型名称、API Base、ASIL 等级等参数。选择 ASIL 等级时 Temperature 会自动联动为推荐值。

> API Key 仅保存在后端内存中，不会写入磁盘。

### JSON 导入 / 导出

支持上传 JSON 配置文件一键导入；也可导出当前配置（API Key 自动脱敏）。示例格式：

```json
{
  "provider": "deepseek",
  "api_key": "sk-xxx",
  "api_keys": ["sk-key1", "sk-key2"],
  "api_base": "https://api.deepseek.com/v1",
  "model": "deepseek-v4-pro"
}
```

## API 概览

后端提供 RESTful + SSE 接口（默认 `http://127.0.0.1:8000`）：

| 分类 | 端点（节选） |
|------|------|
| 配置 | `GET/PUT /api/config`、`POST /api/config/import`、`GET /api/config/export` |
| 上传 | `POST /api/upload/{files,zip,local-path,paste}`、`GET /api/upload/pick` |
| 模块 | `GET /api/modules`、`POST /api/modules/{merge,rename,delete}`、`PUT /api/modules/{active,selected}`、`GET /api/modules/{name}/{code,analysis}` |
| 预估 | `GET /api/estimate/agent/{agent}`、`GET /api/estimate/batch` |
| 生成 | `GET /api/generate/{agent}/stream`（SSE）、`GET /api/generate/batch/stream`（SSE）、`POST /api/generate/cancel` |
| 文档 | `GET /api/docs`、`GET /api/docs/{module}/{agent}`、`POST /api/validate/cross` |
| 导出 | `GET /api/export/{word,excel,zip}` |
| 其他 | `GET /api/history`、`GET/POST/DELETE /api/templates/{agent}` |

SSE 事件类型：`status` / `token` / `chunk_init` / `merge_start` / `progress` / `done` / `batch_done` / `error`。

## 常见问题

**Q: 双击启动脚本提示「未检测到 Python」？**
本机未安装 Python 或未加入 PATH。请前往 [python.org](https://www.python.org/downloads/) 下载安装，安装时务必勾选 **Add python.exe to PATH**，完成后重新双击 `启动工具.bat`。

**Q: 依赖安装失败？**
脚本会先用默认源安装，失败后自动切换清华镜像源重试。若仍失败，请检查网络连接（如公司代理），然后重新运行 `启动工具.bat`，脚本会自动续装缺失的依赖。

**Q: 浏览器没有自动打开？**
手动在浏览器地址栏输入 `http://localhost:8000`。

**Q: 页面样式或代码高亮异常？**
前端 Bootstrap / marked / highlight.js 经 CDN 加载，请确认首屏加载时可访问外网。

**Q: 提示端口被占用？**
程序会自动尝试 8000~8010 端口；也可手动指定：
```powershell
cd src
..\.venv\Scripts\python -m uvicorn server.main:app --host 127.0.0.1 --port 8001
```

**Q: 如何停止程序？**
关闭命令行窗口，或在命令行按 `Ctrl+C`。

**Q: 如何在「单文档工作台」同时选中多个模块？**
按住 **Ctrl** 键再点击模块 Chip，可多选模块（用于批量生成）。普通点击为单选（其他自动取消）。

**Q: 上传代码后模块列表没有更新？**
上传完成后模块应自动加载；若未显示，刷新浏览器页面即可。

**Q: 如何清除已上传的代码？**
在「工程总览」页面底部点击 **清除上传** 按钮，将清空所有已上传代码和检测到的模块。

**Q: 生成过程中如何取消？**
点击生成面板中的 **取消** 按钮，或批量生成中点击 **取消全部**，当前正在生成的 Agent 会在下一个 token 处停止。

**Q: 腾讯电脑管家导致页面通信异常？**
腾讯电脑管家（QQPCTray）的"网页防护"功能可能拦截本地 WebSocket / SSE 长连接。**临时关闭腾讯电脑管家**或在其设置中关闭网页防护即可恢复。

**Q: 切换到不同模块 Chip 时，预估数据不更新？**
请确认已刷新浏览器缓存（`Ctrl+F5` 强制刷新）。预估是根据模块代码量动态计算的，不同模块的 Token 数和预计输出会不同。

## 项目结构

```
fusa_sw_doc_generate_tool/
├── .venv/                    # Python 虚拟环境
├── src/
│   ├── server/               # FastAPI 后端
│   │   ├── main.py           # 应用入口（挂载路由 + 静态前端）
│   │   ├── state.py          # 应用状态单例（替代 session_state + 持久化）
│   │   ├── estimate.py       # Token 预估纯逻辑 + Agent 元数据
│   │   ├── upload.py         # 上传与模块检测（文件/ZIP/本地/粘贴）
│   │   ├── generation.py     # LLM 生成编排（单/分段/审查/批量 SSE）
│   │   ├── models.py         # Pydantic 请求/响应模型
│   │   ├── sse.py            # SSE 事件格式化与响应封装
│   │   └── routers/          # 按域拆分的路由（config/upload/modules/…）
│   ├── webui/                # 前端单页应用（静态资源）
│   │   ├── index.html        # 布局（配置栏 + 工程总览/工作台双视图）
│   │   ├── css/style.css     # 样式（卡片 / 免责声明 / 暗色适配）
│   │   └── js/               # api / state / sidebar / dashboard / workspace / main
│   ├── prompts/              # Prompt 模板包（按 Agent 拆分）
│   │   ├── __init__.py       # PromptManager（调度 + 分段 + 审查 + 合并）
│   │   ├── _base.py          # 共享常量（ASIL 要求、覆盖率、AI-AP 表）
│   │   └── srs.py / sad.py / fmea.py / dfa.py / sdd.py / tc_unit.py / tc_integration.py
│   ├── safety_knowledge.py   # 功能安全领域知识库（失效模式/DC/ASIL分解）
│   ├── llm_engine.py         # LLM 调用引擎（流式 + 重试 + 缓存）
│   ├── code_parser.py        # C/C++ 代码解析（tree-sitter AST）
│   ├── module_detector.py    # 多文件工程的模块识别与代码聚合
│   ├── validator.py          # ISO 26262 / ASPICE 质量校验 + 跨文档追溯
│   ├── doc_exporter.py       # 文档导出（Word / Excel）
│   └── template_parser.py    # 自定义模板解析
├── saved_results.json        # 已生成文档与历史持久化（自动生成）
├── generation_log.jsonl      # 生成日志（自动生成）
├── requirements.txt          # Python 依赖
└── 启动工具.bat              # 一键启动脚本（自动装环境 + 装依赖 + 启动）
```

## 技术栈

- **后端**：FastAPI · Uvicorn · Pydantic · SSE（StreamingResponse）
- **前端**：Bootstrap 5 · 原生 JavaScript · marked.js · highlight.js（均经 CDN）
- **LLM**：openai / anthropic SDK（OpenAI 兼容接口）
- **解析与导出**：tree-sitter（tree-sitter-c / tree-sitter-cpp）· python-docx · openpyxl · lxml

## License

See [LICENSE](LICENSE).
