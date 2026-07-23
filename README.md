# 功能安全文档生成器 v1.0

> ISO 26262 / ASPICE 文档自动生成工具

基于 C/C++ 代码，通过接入大语言模型（LLM），自动生成满足 ISO 26262 和 ASPICE 标准的功能安全文档。

## 支持的文档类型

| 缩写 | 全称 |
|------|------|
| SRS | 软件需求规格说明 |
| SAD | 软件架构设计 |
| FMEA | 失效模式与影响分析 |
| SDD | 软件详细设计 |
| TC | 测试用例 |

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

## 支持的模型

- OpenAI（GPT-4o）
- Anthropic（Claude）
- 通义千问（DashScope）
- DeepSeek
- 智谱 GLM（ChatGLM）
- Kimi（Moonshot）
- 自定义兼容 API

## 导出格式

- Markdown（`.md`）
- Word（`.docx`）
- Excel（`.xlsx`，FMEA 专属）

## 自定义文档模板

支持上传 `.md` / `.txt` / `.docx` / `.xlsx` 格式的文档模板，大模型将按照模板格式输出文档。

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
├── .venv/              # Python 虚拟环境
├── src/
│   ├── app.py          # Streamlit 主界面
│   ├── llm_engine.py   # LLM 调用引擎
│   ├── code_parser.py  # C/C++ 代码解析
│   ├── prompts.py      # Prompt 模板管理
│   ├── doc_exporter.py # 文档导出（Word/Excel）
│   └── template_parser.py # 自定义模板解析
├── requirements.txt    # Python 依赖
└── 启动工具.bat        # 一键启动脚本
```

## License

See [LICENSE](LICENSE).
