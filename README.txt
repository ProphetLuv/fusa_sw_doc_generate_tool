============================================
  功能安全文档生成器 v1.0
  ISO 26262 / ASPICE 文档自动生成工具
============================================

【使用方法】
  1. 双击 "启动工具.bat"
  2. 等待命令行显示 "Uvicorn server started"
  3. 浏览器打开 http://localhost:8501
  4. 在侧边栏选择模型提供商并输入 API Key
  5. 上传 C/C++ 代码文件，点击生成

【支持的模型】
  - OpenAI (GPT-4o)
  - Anthropic (Claude)
  - 通义千问 (DashScope)
  - DeepSeek
  - 智谱 GLM (ChatGLM)
  - Kimi (Moonshot)
  - 自定义兼容 API

【支持的文档类型】
  - SRS: 软件需求规格说明
  - FMEA: 失效模式与影响分析
  - SDD: 软件详细设计
  - TC: 测试用例

【导出格式】
  - Markdown (.md)
  - Word (.docx)
  - Excel (.xlsx, FMEA专属)

【自定义文档模板】
  支持上传 .md / .txt / .docx / .xlsx 格式的文档模板
  大模型将按照模板格式输出文档

【配置方式】
  - 手动填写: 在侧边栏逐项填写
  - JSON 导入: 上传配置文件，示例格式如下

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

【常见问题】
  Q: 浏览器没有自动打开?
  A: 手动在浏览器地址栏输入 http://localhost:8501

  Q: 提示端口被占用?
  A: 关闭其他占用8501端口的程序，或修改启动参数添加 --server.port 8502

  Q: 如何停止程序?
  A: 关闭命令行窗口即可

【系统要求】
  - Windows 10/11
  - 现代浏览器 (Chrome/Edge/Firefox)
  - 无需安装 Python（已内置运行环境）
