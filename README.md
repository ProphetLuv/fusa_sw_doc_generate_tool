# 功能安全文档生成器 v2.0

> ISO 26262 / ASPICE 文档自动生成工具

基于 C/C++ 代码，通过接入大语言模型（LLM），自动生成满足 ISO 26262 和 ASPICE 标准的功能安全文档。

## 支持的文档类型

| 缩写 | 全称 |
|------|------|
| SRS | 软件需求规格说明 |
| SAD | 软件架构设计 |
| FMEA | 失效模式与影响分析 |
| DFA | 相关失效分析（CCF / 级联 / 单点 / FFI） |
| SDD | 软件详细设计 |
| TC-UNIT | 单元测试用例（含 FMEA 导出故障注入） |
| TC-INTEGRATION | 集成测试用例（含 DFA 级联失效验证） |

## 系统要求

- Windows 10 / 11
- Python ≥ 3.13（基于 `requirements.txt` 配置虚拟环境）
- 现代浏览器（Chrome / Edge / Firefox）

## 快速开始

### 1. 配置 Python 环境

```powershell
cd fusa_sw_doc_generate_tool
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. 启动程序

双击 `启动工具.bat`，等待命令行显示：

```
Uvicorn server started on :::8501
```

然后在浏览器打开 [http://localhost:8501](http://localhost:8501)。

> 若 8501 端口被占用，程序会自动尝试 8502~8510 端口，并在命令行显示实际地址。

### 3. 使用

1. 在侧边栏选择**模型提供商**并输入 **API Key**
2. 上传 C/C++ 代码文件
3. 选择需要生成的文档类型，点击**生成**

## 核心特性

- **7 种文档类型**：SRS / SAD / FMEA / DFA / SDD / TC-UNIT / TC-INTEGRATION
- **多模型支持**：OpenAI / Anthropic / 通义千问 / DeepSeek / 智谱 GLM / Kimi / 自定义 API
- **多 Key 轮询**：配置多个 API Key，自动轮询提升并发上限
- **并行生成**：仪表盘支持多文档并行生成，大幅缩短等待时间
- **安全知识库注入**：内置失效模式库、安全机制 DC 表、ASIL 分解规则，降低 LLM 幻觉
- **跨文档追溯校验**：自动检查 SRS→FMEA→DFA→TC 的 ID 引用覆盖率
- **代码-文档一致性**：检测 LLM 虚构函数（幻觉），验证高复杂度函数的文档覆盖
- **故障注入测试导出**：TC-UNIT/TC-INTEGRATION 从 FMEA/DFA 逐条导出结构化故障注入用例
- **分段一致性合并**：多段并发生成后自动执行术语/编号/交叉引用一致性审查
- **Token 精准预估**：计入知识库、前置文档、多轮调用，误差 < 10%
- **质量校验**：内置 ISO 26262 / ASPICE 合规校验（ID 格式、RPN 范围、追溯性等）
- **AST 级代码解析**：基于 tree-sitter 精确提取函数、结构体、宏定义
- **自定义模板**：上传 .md / .txt / .text / .rst / .docx / .xlsx 模板，按模板格式输出
- **多格式导出**：Markdown / Word（.docx）/ Excel（.xlsx，FMEA 专属）
- **生成历史**：自动记录每次生成的配置与结果，支持查看与回溯

## 配置方式

### 手动填写

在侧边栏逐项填写提供商、API Key、模型名称等参数。

### JSON 导入

上传配置文件，示例格式：

```json
{
  "provider": "deepseek",
  "api_key": "sk-xxx",
  "api_base": "https://api.deepseek.com/v1",
  "model": "deepseek-v4-pro",
  "max_tokens": 8192,
  "temperature": 0.2,
  "module_name": "MotorController",
  "asil_level": "ASIL B",
  "doc_types": ["SRS", "FMEA"]
}
```

## 常见问题

**Q: 浏览器没有自动打开？**
手动在浏览器地址栏输入 `http://localhost:8501`

**Q: 提示端口被占用？**
程序会自动尝试 8501~8510 端口；也可手动指定：
```powershell
.venv\Scripts\streamlit.exe run src\app.py --server.port 8502
```

**Q: 如何停止程序？**
关闭命令行窗口即可。

## 项目结构

```
fusa_sw_doc_generate_tool/
├── .venv/                  # Python 虚拟环境
├── src/
│   ├── app.py              # 入口文件（页面配置 + CSS + 模块调度）
│   ├── app/                # UI 模块包
│   │   ├── __init__.py
│   │   ├── app_utils.py    # 工具函数、常量、Token 预估、持久化
│   │   ├── app_sidebar.py  # 侧边栏配置面板
│   │   ├── app_dashboard.py# 仪表盘与批量并行生成
│   │   ├── app_workspace.py# Agent 工作区与单文档生成
│   │   └── app_results.py  # 结果展示与历史记录
│   ├── prompts/            # Prompt 模板包（按 Agent 拆分）
│   │   ├── __init__.py     # PromptManager（调度 + 分段 + 审查 + 合并）
│   │   ├── _base.py        # 共享常量（ASIL 要求、覆盖率、AI-AP 表）
│   │   ├── srs.py          # SRS Prompt
│   │   ├── sad.py          # SAD Prompt
│   │   ├── fmea.py         # FMEA Prompt
│   │   ├── dfa.py          # DFA Prompt
│   │   ├── sdd.py          # SDD Prompt
│   │   ├── tc_unit.py      # TC-UNIT Prompt
│   │   └── tc_integration.py # TC-INTEGRATION Prompt
│   ├── safety_knowledge.py # 功能安全领域知识库（失效模式/DC/ASIL分解）
│   ├── llm_engine.py       # LLM 调用引擎（流式 + 重试 + 缓存）
│   ├── code_parser.py      # C/C++ 代码解析（tree-sitter AST）
│   ├── validator.py        # ISO 26262 / ASPICE 质量校验 + 跨文档追溯
│   ├── doc_exporter.py     # 文档导出（Word / Excel）
│   └── template_parser.py  # 自定义模板解析
├── requirements.txt        # Python 依赖
└── 启动工具.bat            # 一键启动脚本
```

## License

See [LICENSE](LICENSE).
