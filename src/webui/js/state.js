/* ==================================================================
   state.js — 前端应用状态（单一数据源，变化时局部重渲染）
   ================================================================== */

const AGENT_ORDER = ["SRS", "SAD", "FMEA", "DFA", "SDD", "TC-UNIT", "TC-INTEGRATION"];

const AGENT_META = {
  "SRS":  { icon: "📋", name: "SRS Agent", full: "软件需求规格说明",
            desc: "从代码提取功能需求、接口需求、安全需求，生成完整的 SRS 文档",
            color: "linear-gradient(135deg, #3a4a6b 0%, #4a4068 100%)" },
  "SAD":  { icon: "🏗️", name: "SAD Agent", full: "软件架构设计",
            desc: "分析模块分解、组件接口、数据流、中断调度，生成架构设计文档",
            color: "linear-gradient(135deg, #6b4a58 0%, #5a3d50 100%)" },
  "FMEA": { icon: "⚠️", name: "FMEA Agent", full: "失效模式与影响分析",
            desc: "识别失效模式、评估 RPN、制定缓解措施（自动注入 SRS + SAD 上下文）",
            color: "linear-gradient(135deg, #3d5a6b 0%, #3a5260 100%)" },
  "DFA":  { icon: "🔗", name: "DFA Agent", full: "相关失效分析",
            desc: "CCF/级联/单点/FFI 四维分析（自动注入 SAD + FMEA 上下文）",
            color: "linear-gradient(135deg, #4a3d6b 0%, #3d3560 100%)" },
  "SDD":  { icon: "📐", name: "SDD Agent", full: "软件详细设计",
            desc: "深入分析函数级设计、数据结构、算法逻辑，生成详细设计文档",
            color: "linear-gradient(135deg, #3d6b5a 0%, #3a5a50 100%)" },
  "TC-UNIT": { icon: "🧪", name: "TC-UNIT Agent", full: "单元测试用例",
            desc: "针对每个函数设计单元测试，含 Unity/GTest 代码、覆盖矩阵和通过准则",
            color: "linear-gradient(135deg, #6b5a4a 0%, #5a4a3d 100%)" },
  "TC-INTEGRATION": { icon: "🔗", name: "TC-INTEG Agent", full: "集成测试用例",
            desc: "验证模块间接口、数据流、控制流、时序与故障注入的集成测试",
            color: "linear-gradient(135deg, #5a5a3d 0%, #4a4a35 100%)" },
};

const ASIL_LEVELS = ["QM", "ASIL A", "ASIL B", "ASIL C", "ASIL D"];
const ASIL_TEMP = { "QM": 0.30, "ASIL A": 0.20, "ASIL B": 0.15, "ASIL C": 0.10, "ASIL D": 0.05 };
const ASIL_TEMP_HINT = {
  "QM": "可适当提高创造性（0.3~0.5）", "ASIL A": "建议 0.2~0.3",
  "ASIL B": "建议 0.1~0.2，确保准确性", "ASIL C": "建议 0.1~0.15，高确定性",
  "ASIL D": "建议 0.0~0.1，最高确定性",
};
const PROVIDERS = ["openai", "anthropic", "dashscope", "deepseek", "glm", "kimi"];

const Store = {
  view: "dashboard",              // dashboard | workspace
  config: {},                     // 后端配置
  providerBaseUrls: {},
  defaultModels: {},

  // 模块快照
  modules: [],                    // [{name, files, file_count, lines, prefix, doc_count}]
  activeModule: null,
  selectedModules: [],
  hasCode: false,
  defaultModuleName: "目标模块",

  docsOverview: {},               // {module: doc_count}
  templates: {},                  // {agent: chars}

  // workspace 当前 agent
  wsAgent: "SRS",

  // 运行时缓存
  codeCache: {},                  // {module: code}
  generating: false,
  currentSSE: null,

  // 订阅者（视图重渲染回调）
  _subs: {},
  on(evt, fn) { (this._subs[evt] = this._subs[evt] || []).push(fn); },
  emit(evt, payload) { (this._subs[evt] || []).forEach((fn) => fn(payload)); },

  applyModulesSnapshot(snap) {
    if (!snap) return;
    this.modules = snap.modules || [];
    this.activeModule = snap.active_module || null;
    this.selectedModules = snap.selected_modules || [];
    this.hasCode = !!snap.has_code;
    this.defaultModuleName = snap.default_module_name || "目标模块";
    this.emit("modules");
  },

  getActiveModuleObj() {
    return this.modules.find((m) => m.name === this.activeModule) || null;
  },
};
