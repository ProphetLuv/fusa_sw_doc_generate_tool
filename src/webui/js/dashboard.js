/* ==================================================================
   dashboard.js — 工程总览视图
   上传（文件/ZIP/本地/粘贴）· 模块管理 · Token 预估 · 7 卡片
   · 一键批量生成（SSE）· 打包下载 · 跨文档校验 · 清空
   ================================================================== */

const Dashboard = {
  el() { return document.getElementById("view-dashboard"); },
  _batchSSE: null,

  render() {
    this.el().innerHTML = `
      <h1 class="main-title">🛡️ 软件功能安全文档生成器</h1>
      <p class="sub-title">ISO 26262 / ASPICE · 从 C/C++ 代码自动生成功能安全文档</p>

      <!-- 上传区 -->
      <div class="card mb-3"><div class="card-body">
        <h6 class="card-title">📥 代码上传</h6>
        <ul class="nav nav-tabs mb-3" id="upload-tabs">
          <li class="nav-item"><button class="nav-link active" data-up="files">多文件</button></li>
          <li class="nav-item"><button class="nav-link" data-up="zip">ZIP 包</button></li>
          <li class="nav-item"><button class="nav-link" data-up="local">本地路径</button></li>
          <li class="nav-item"><button class="nav-link" data-up="paste">粘贴代码</button></li>
        </ul>
        <div id="upload-panels"></div>
      </div></div>

      <!-- 模块与统计 -->
      <div id="dash-modules"></div>

      <!-- Agent 卡片 -->
      <div id="dash-agents" class="mb-3"></div>

      <!-- 批量操作 -->
      <div id="dash-actions"></div>

      <!-- 批量进度 / 结果 -->
      <div id="batch-panel" class="mt-3"></div>

      <!-- 跨文档校验结果 -->
      <div id="cross-panel" class="mt-3"></div>
    `;
    this.renderUploadPanel("files");
    this.renderModules();
    this.renderAgents();
    this.renderActions();
    this.bindTabs();
  },

  bindTabs() {
    this.el().querySelectorAll("#upload-tabs button").forEach((b) => {
      b.addEventListener("click", () => {
        this.el().querySelectorAll("#upload-tabs button").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        this.renderUploadPanel(b.dataset.up);
      });
    });
  },

  /* ---------------- 上传面板 ---------------- */
  renderUploadPanel(kind) {
    const p = document.getElementById("upload-panels");
    if (kind === "files") {
      p.innerHTML = `
        <input type="file" class="form-control" id="up-files" multiple
               accept=".c,.h,.cpp,.hpp,.cc,.cxx" />
        <div class="form-text">支持多选 .c/.h/.cpp 等源文件</div>`;
      document.getElementById("up-files").addEventListener("change", (e) => {
        if (e.target.files.length) this.doUpload(() => API.uploadFiles(e.target.files));
      });
    } else if (kind === "zip") {
      p.innerHTML = `<input type="file" class="form-control" id="up-zip" accept=".zip" />`;
      document.getElementById("up-zip").addEventListener("change", (e) => {
        if (e.target.files[0]) this.doUpload(() => API.uploadZip(e.target.files[0]));
      });
    } else if (kind === "local") {
      p.innerHTML = `
        <div class="input-group">
          <input type="text" class="form-control" id="up-local" placeholder="本机 .zip 或文件夹绝对路径" />
          <button class="btn btn-outline-secondary" id="up-pick-zip">选 ZIP</button>
          <button class="btn btn-outline-secondary" id="up-pick-dir">选文件夹</button>
          <button class="btn btn-primary" id="up-local-go">导入</button>
        </div>
        <div class="form-text">仅限本机运行场景（弹出系统文件对话框）</div>`;
      const pick = async (mode) => {
        try {
          UI.overlay(true, "等待选择...");
          const r = await API.pickLocalPath(mode);
          UI.overlay(false);
          if (r.path) { document.getElementById("up-local").value = r.path; }
        } catch (err) { UI.overlay(false); UI.toast(err.message, "error"); }
      };
      document.getElementById("up-pick-zip").addEventListener("click", () => pick("zip"));
      document.getElementById("up-pick-dir").addEventListener("click", () => pick("dir"));
      document.getElementById("up-local-go").addEventListener("click", () => {
        const path = document.getElementById("up-local").value.trim();
        if (path) this.doUpload(() => API.uploadLocalPath(path));
      });
    } else if (kind === "paste") {
      p.innerHTML = `
        <input type="text" class="form-control mb-2" id="up-paste-name" placeholder="模块名（可选）" />
        <textarea class="form-control" id="up-paste-code" rows="8" placeholder="粘贴 C/C++ 代码..."></textarea>
        <button class="btn btn-primary btn-sm mt-2" id="up-paste-go">导入代码</button>`;
      document.getElementById("up-paste-go").addEventListener("click", () => {
        const code = document.getElementById("up-paste-code").value;
        const name = document.getElementById("up-paste-name").value.trim();
        if (!code.trim()) { UI.toast("请粘贴代码", "warn"); return; }
        this.doUpload(() => API.uploadPaste(code, name || null));
      });
    }
  },

  async doUpload(fn) {
    try {
      UI.overlay(true, "解析代码与检测模块...");
      const snap = await fn();
      Store.applyModulesSnapshot(snap);
      Store.codeCache = {};
      const skipped = (snap.skipped && snap.skipped.length) ? `（跳过 ${snap.skipped.length} 个非源文件）` : "";
      UI.toast(`识别出 ${snap.modules.length} 个模块${skipped}`, "success");
      await Dashboard.refreshDocsOverview();
      Dashboard.renderModules();
      Dashboard.renderAgents();
      Dashboard.renderActions();
    } catch (err) {
      UI.toast("上传失败: " + err.message, "error");
    } finally {
      UI.overlay(false);
    }
  },

  /* ---------------- 模块与统计 ---------------- */
  renderModules() {
    const box = document.getElementById("dash-modules");
    if (!box) return;
    if (!Store.modules.length) {
      box.innerHTML = `<div class="alert alert-secondary">尚未上传代码。请在上方选择一种方式导入 C/C++ 代码。</div>`;
      return;
    }
    const totalFiles = Store.modules.reduce((s, m) => s + m.file_count, 0);
    const totalLines = Store.modules.reduce((s, m) => s + m.lines, 0);
    const totalDocs = Store.modules.reduce((s, m) => s + m.doc_count, 0);

    box.innerHTML = `
      <div class="row g-2 mb-3">
        <div class="col"><div class="metric-card"><div class="metric-value">${Store.modules.length}</div><div class="metric-label">模块</div></div></div>
        <div class="col"><div class="metric-card"><div class="metric-value">${totalFiles}</div><div class="metric-label">源文件</div></div></div>
        <div class="col"><div class="metric-card"><div class="metric-value">${totalLines}</div><div class="metric-label">代码行</div></div></div>
        <div class="col"><div class="metric-card"><div class="metric-value">${totalDocs}</div><div class="metric-label">已生成文档</div></div></div>
      </div>

      <div class="card mb-3"><div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h6 class="card-title mb-0">📦 模块管理</h6>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary" id="mod-merge">合并所选</button>
            <button class="btn btn-outline-danger" id="mod-clear">清空代码</button>
          </div>
        </div>
        <div class="module-list" id="module-list"></div>
      </div></div>

      <div id="code-preview-box"></div>
    `;
    this.renderModuleList();
    document.getElementById("mod-merge").addEventListener("click", () => this.mergeSelected());
    document.getElementById("mod-clear").addEventListener("click", () => this.clearCode());
  },

  renderModuleList() {
    const list = document.getElementById("module-list");
    if (!list) return;
    list.innerHTML = Store.modules.map((m) => {
      const active = m.name === Store.activeModule;
      const checked = Store.selectedModules.includes(m.name) ? "checked" : "";
      return `
      <div class="module-row ${active ? "active" : ""}" data-mod="${UI.esc(m.name)}">
        <div class="d-flex align-items-center gap-2">
          <input class="form-check-input mt-0 mod-select" type="checkbox" ${checked} data-mod="${UI.esc(m.name)}" title="批量范围" />
          <div class="flex-fill mod-open" data-mod="${UI.esc(m.name)}">
            <div class="mod-name">${UI.esc(m.name)} ${active ? '<span class="badge text-bg-primary">活动</span>' : ""}</div>
            <div class="mod-meta">${m.file_count} 文件 · ${m.lines} 行 · ${m.doc_count} 文档 · 前缀 ${UI.esc(m.prefix)}</div>
          </div>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-outline-secondary mod-rename" data-mod="${UI.esc(m.name)}">重命名</button>
            <button class="btn btn-outline-danger mod-del" data-mod="${UI.esc(m.name)}">删除</button>
          </div>
        </div>
      </div>`;
    }).join("");

    list.querySelectorAll(".mod-open").forEach((el) =>
      el.addEventListener("click", () => this.selectActive(el.dataset.mod)));
    list.querySelectorAll(".mod-select").forEach((el) =>
      el.addEventListener("change", () => this.toggleSelected()));
    list.querySelectorAll(".mod-rename").forEach((el) =>
      el.addEventListener("click", (e) => { e.stopPropagation(); this.renameMod(el.dataset.mod); }));
    list.querySelectorAll(".mod-del").forEach((el) =>
      el.addEventListener("click", (e) => { e.stopPropagation(); this.deleteMod(el.dataset.mod); }));
  },

  async selectActive(name) {
    if (name === Store.activeModule) { this.previewCode(name); return; }
    try {
      const snap = await API.setActiveModule(name);
      Store.applyModulesSnapshot(snap);
      this.renderModules();
      this.renderAgents();
      this.previewCode(name);
      this.refreshEstimate();
    } catch (err) { UI.toast(err.message, "error"); }
  },

  async toggleSelected() {
    const sel = Array.from(document.querySelectorAll(".mod-select:checked")).map((c) => c.dataset.mod);
    try {
      const snap = await API.setSelectedModules(sel);
      Store.applyModulesSnapshot(snap);
    } catch (err) { UI.toast(err.message, "error"); }
  },

  async mergeSelected() {
    const sel = Store.selectedModules;
    if (sel.length < 2) { UI.toast("请至少勾选两个模块", "warn"); return; }
    const newName = prompt("合并后的模块名：", sel[0] + "_merged");
    if (!newName) return;
    try {
      const snap = await API.mergeModules(sel, newName.trim());
      Store.applyModulesSnapshot(snap);
      Store.codeCache = {};
      this.renderModules(); this.renderAgents();
      UI.toast("模块已合并", "success");
    } catch (err) { UI.toast(err.message, "error"); }
  },

  async renameMod(name) {
    const newName = prompt("新模块名：", name);
    if (!newName || newName.trim() === name) return;
    try {
      const snap = await API.renameModule(name, newName.trim());
      Store.applyModulesSnapshot(snap);
      this.renderModules(); this.renderAgents();
      UI.toast("已重命名", "success");
    } catch (err) { UI.toast(err.message, "error"); }
  },

  async deleteMod(name) {
    if (!confirm(`确认删除模块「${name}」？其已生成文档也将移除。`)) return;
    try {
      const snap = await API.deleteModule(name);
      Store.applyModulesSnapshot(snap);
      delete Store.codeCache[name];
      this.renderModules(); this.renderAgents();
      UI.toast("已删除", "success");
    } catch (err) { UI.toast(err.message, "error"); }
  },

  async clearCode() {
    if (!confirm("确认清空所有已上传代码与模块？")) return;
    try {
      const snap = await API.clearUpload();
      Store.applyModulesSnapshot(snap);
      Store.codeCache = {};
      this.render();
      UI.toast("已清空代码", "success");
    } catch (err) { UI.toast(err.message, "error"); }
  },

  /* ---------------- 按需代码预览（懒加载 + 缓存 + 文件级切换） ---------------- */
  async previewCode(name) {
    const box = document.getElementById("code-preview-box");
    if (!box) return;
    box.innerHTML = `<div class="card"><div class="card-body">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h6 class="mb-0">🔍 代码预览：${UI.esc(name)}</h6>
        <button class="btn btn-sm btn-outline-secondary" id="analyze-btn">代码分析</button>
      </div>
      <div id="file-picker-row" class="mb-2"></div>
      <div id="code-preview-content"><div class="text-muted small">加载中...</div></div>
      <div id="analysis-box" class="mt-2"></div>
    </div></div>`;
    document.getElementById("analyze-btn").addEventListener("click", () => this.analyzeCode(name));
    try {
      let code = Store.codeCache[name];
      if (code == null) {
        const r = await API.getModuleCode(name);
        code = r.code; Store.codeCache[name] = code;
      }
      const files = this._splitModuleFiles(code);
      const render = (text) => {
        const cc = document.getElementById("code-preview-content");
        if (!cc) return;
        const preview = text.length > 20000 ? text.slice(0, 20000) + "\n... (已截断)" : text;
        cc.innerHTML = `<pre class="doc-render" style="max-height:360px"><code class="language-c"></code></pre>`;
        cc.querySelector("code").textContent = preview;
        if (window.hljs) hljs.highlightElement(cc.querySelector("code"));
      };
      const row = document.getElementById("file-picker-row");
      if (files.length > 1) {
        row.innerHTML = `<div class="input-group input-group-sm">
          <span class="input-group-text">📄 文件</span>
          <select class="form-select" id="file-picker">
            <option value="__all__">全部（合并视图 · ${files.length} 个文件）</option>
            ${files.map((f, i) => `<option value="${i}">${UI.esc(f.path)}</option>`).join("")}
          </select>
        </div>`;
        document.getElementById("file-picker").addEventListener("change", (e) => {
          const v = e.target.value;
          render(v === "__all__" ? code : (files[Number(v)] ? files[Number(v)].content : ""));
        });
      } else {
        row.innerHTML = "";
      }
      render(code);
    } catch (err) { UI.toast(err.message, "error"); }
  },

  /* 将模块合并代码按 `// ===== path =====` 分隔符切分为单文件列表 */
  _splitModuleFiles(code) {
    if (!code) return [];
    const parts = code.split(/\/\/ ===== (.+?) =====\n/);
    const files = [];
    for (let i = 1; i < parts.length - 1; i += 2) {
      files.push({ path: (parts[i] || "").trim(), content: (parts[i + 1] || "").replace(/\s+$/, "") });
    }
    return files;
  },

  async analyzeCode(name) {
    const box = document.getElementById("analysis-box");
    box.innerHTML = `<div class="text-muted small">分析中...</div>`;
    try {
      const r = await API.getModuleAnalysis(name);
      const a = r.analysis || {};
      box.innerHTML = `<div class="alert alert-info small mb-0">
        📊 函数 ${a.functions || 0} · 结构体 ${a.structs || 0} · 全局变量 ${a.global_vars || 0}
        · 宏 ${a.macros || 0} · 平均复杂度 ${a.avg_complexity || 0} · 最大 ${UI.esc(String(a.max_complexity || "-"))}
        · ${a.lines || 0} 行 · 约 ${r.size_kb} KB</div>`;
    } catch (err) { box.innerHTML = `<div class="text-danger small">分析失败: ${UI.esc(err.message)}</div>`; }
  },

  /* ---------------- Agent 卡片 ---------------- */
  renderAgents() {
    const box = document.getElementById("dash-agents");
    if (!box) return;
    box.innerHTML = `<h6 class="mb-2">🤖 7-Agent 文档矩阵${Store.activeModule ? `（活动模块：${UI.esc(Store.activeModule)}）` : ""}</h6>
      <div class="agent-grid">${AGENT_ORDER.map((a) => this.agentCard(a)).join("")}</div>`;
    box.querySelectorAll("[data-agent-go]").forEach((b) =>
      b.addEventListener("click", () => {
        Store.wsAgent = b.dataset.agentGo;
        Router.go("workspace");
      }));
  },

  agentCard(a) {
    const m = AGENT_META[a];
    const activeObj = Store.getActiveModuleObj();
    const done = activeObj && Store.docsOverview[Store.activeModule] ? "" : "";
    return `
    <div class="agent-card" style="background:${m.color}">
      <div class="agent-icon">${m.icon}</div>
      <div class="agent-name">${m.name}</div>
      <div class="agent-full">${m.full}</div>
      <div class="agent-desc">${m.desc}</div>
      <div class="agent-foot">
        <span class="agent-badge">${a}</span>
        <button class="btn btn-sm btn-light" data-agent-go="${a}">生成 →</button>
      </div>
    </div>`;
  },

  /* ---------------- 批量操作 & 预估 ---------------- */
  renderActions() {
    const box = document.getElementById("dash-actions");
    if (!box) return;
    if (!Store.hasCode) { box.innerHTML = ""; return; }
    box.innerHTML = `
      <div class="card"><div class="card-body">
        <h6 class="card-title">⚙️ 批量与导出</h6>
        <div id="est-box" class="mb-2 small text-muted">Token 预估加载中...</div>
        <div class="mb-2">
          <div class="d-flex align-items-center gap-2 mb-1">
            <label class="section-label mb-0">Agent 范围</label>
            <button class="btn btn-link btn-sm p-0" id="batch-agent-all">全选</button>
            <span class="text-muted">·</span>
            <button class="btn btn-link btn-sm p-0" id="batch-agent-none">清空</button>
          </div>
          <div id="batch-agent-chips" class="d-flex flex-wrap gap-1">
            ${AGENT_ORDER.map((a) => `<button type="button" class="btn btn-sm btn-primary batch-agent-chip active" data-agent="${a}">${a}</button>`).join("")}
          </div>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <button class="btn btn-primary btn-sm" id="btn-batch">🚀 批量生成（所选模块 × 所选 Agent）</button>
          <button class="btn btn-danger btn-sm d-none" id="btn-cancel">⏹ 取消</button>
          <button class="btn btn-outline-secondary btn-sm" id="btn-cross">🔗 跨文档校验</button>
          <button class="btn btn-outline-success btn-sm" id="btn-zip">📦 打包下载全部</button>
          <button class="btn btn-outline-danger btn-sm" id="btn-clear-docs">🗑 清空文档</button>
        </div>
      </div></div>`;
    this._bindAgentChips();
    document.getElementById("btn-batch").addEventListener("click", () => this.runBatch());
    document.getElementById("btn-cancel").addEventListener("click", () => this.cancelBatch());
    document.getElementById("btn-cross").addEventListener("click", () => this.crossValidate());
    document.getElementById("btn-zip").addEventListener("click", () => UI.download(API.downloadUrl("zip"), "全部文档.zip"));
    document.getElementById("btn-clear-docs").addEventListener("click", () => this.clearDocs());
    this.refreshEstimate();
  },

  /* Agent 范围 chips：切换 / 全选 / 清空 */
  _bindAgentChips() {
    const setChip = (chip, on) => {
      chip.classList.toggle("active", on);
      chip.classList.toggle("btn-primary", on);
      chip.classList.toggle("btn-outline-primary", !on);
    };
    document.querySelectorAll(".batch-agent-chip").forEach((chip) =>
      chip.addEventListener("click", () => setChip(chip, !chip.classList.contains("active"))));
    const all = document.getElementById("batch-agent-all");
    const none = document.getElementById("batch-agent-none");
    if (all) all.addEventListener("click", () =>
      document.querySelectorAll(".batch-agent-chip").forEach((c) => setChip(c, true)));
    if (none) none.addEventListener("click", () =>
      document.querySelectorAll(".batch-agent-chip").forEach((c) => setChip(c, false)));
  },

  _selectedBatchAgents() {
    return Array.from(document.querySelectorAll(".batch-agent-chip.active")).map((c) => c.dataset.agent);
  },

  async refreshEstimate() {
    const box = document.getElementById("est-box");
    if (!box) return;
    try {
      const single = Store.modules.length <= 1;
      const r = await API.estimateBatch(single ? Store.activeModule : null);
      const scope = r.scope === "project" ? `全工程（${r.module_count} 模块）` : "当前模块";
      box.innerHTML = `📊 批量预估（${scope}）：约 <b>${r.total.toLocaleString()}</b> tokens · 预计成本 <b>${r.cost || "-"}</b>`;
    } catch (err) { box.textContent = "预估不可用: " + err.message; }
  },

  /* ---------------- 批量生成 SSE ---------------- */
  runBatch() {
    if (!Store.config.api_key) { UI.toast("请先在左侧配置 API Key", "warn"); return; }
    if (Store.generating) { UI.toast("已有生成任务在进行", "warn"); return; }
    const agents = this._selectedBatchAgents();
    if (agents.length === 0) { UI.toast("请至少选择一个 Agent", "warn"); return; }
    const full = agents.length === AGENT_ORDER.length;
    Store.generating = true;
    document.getElementById("btn-batch").classList.add("disabled");
    document.getElementById("btn-cancel").classList.remove("d-none");

    const panel = document.getElementById("batch-panel");
    panel.innerHTML = `<div class="card"><div class="card-body">
      <div class="d-flex justify-content-between"><h6 class="mb-2">批量生成进度${full ? "" : `（仅 ${agents.join(", ")}）`}</h6><span id="batch-count"></span></div>
      <div class="progress progress-thin mb-2"><div class="progress-bar" id="batch-bar" style="width:0%"></div></div>
      <div id="batch-status" class="small text-muted"></div>
    </div></div>`;
    const bar = document.getElementById("batch-bar");
    const cnt = document.getElementById("batch-count");
    const st = document.getElementById("batch-status");

    const url = full ? "/api/generate/batch/stream"
      : `/api/generate/batch/stream?agents=${encodeURIComponent(agents.join(","))}`;
    this._batchSSE = openSSE(url, {
      progress: (d) => {
        const pct = Math.round((d.step / d.total) * 100);
        bar.style.width = pct + "%";
        cnt.textContent = `${d.step}/${d.total}`;
        st.textContent = `正在生成：${d.module} · ${d.agent}`;
      },
      status: (d) => { st.textContent = d.message; },
      batch_done: (d) => {
        bar.style.width = "100%";
        bar.classList.add(d.cancelled ? "bg-warning" : "bg-success");
        st.textContent = d.summary;
        this.finishBatch();
        UI.toast(d.summary, d.cancelled ? "warn" : "success");
        this.reloadModulesAndDocs();
      },
      error: (d) => { UI.toast("批量生成错误: " + d.message, "error"); this.finishBatch(); },
      _neterror: () => { if (Store.generating) { this.finishBatch(); } },
    });
  },

  async cancelBatch() {
    try { await API.cancelGeneration(); UI.toast("已发送取消请求", "warn"); }
    catch (err) { UI.toast(err.message, "error"); }
  },

  finishBatch() {
    Store.generating = false;
    if (this._batchSSE) { this._batchSSE.close(); this._batchSSE = null; }
    const b = document.getElementById("btn-batch");
    const c = document.getElementById("btn-cancel");
    if (b) b.classList.remove("disabled");
    if (c) c.classList.add("d-none");
  },

  async reloadModulesAndDocs() {
    try {
      const snap = await API.listModules();
      Store.applyModulesSnapshot(snap);
      await this.refreshDocsOverview();
      this.renderModules();
      this.renderAgents();
    } catch (err) { /* ignore */ }
  },

  async refreshDocsOverview() {
    try {
      const r = await API.listDocs(Store.activeModule);
      Store.docsOverview = r.overview || {};
    } catch (err) { /* ignore */ }
  },

  /* ---------------- 跨文档校验 ---------------- */
  async crossValidate() {
    const panel = document.getElementById("cross-panel");
    panel.innerHTML = `<div class="text-muted small">校验中...</div>`;
    try {
      const r = await API.crossValidate(Store.activeModule);
      panel.innerHTML = `<div class="card"><div class="card-body">
        <h6>🔗 跨文档追溯校验（${UI.esc(r.module)}）</h6>
        <div class="mb-2">${r.passed ? '<span class="badge text-bg-success">通过</span>' : '<span class="badge text-bg-danger">存在问题</span>'} ${UI.esc(r.summary)}</div>
        ${r.results.map((c) => this.checkItem(c)).join("")}
      </div></div>`;
    } catch (err) {
      panel.innerHTML = `<div class="alert alert-warning">${UI.esc(err.message)}</div>`;
    }
  },

  checkItem(c) {
    const cls = c.passed ? "check-pass" : (c.severity === "warning" ? "check-warn" : "check-fail");
    const icon = c.passed ? "✅" : (c.severity === "warning" ? "⚠️" : "❌");
    return `<div class="check-item ${cls}"><span>${icon}</span>
      <div><b>${UI.esc(c.check_name)}</b> — ${UI.esc(c.message)}${c.details ? `<div class="small opacity-75">${UI.esc(c.details)}</div>` : ""}</div></div>`;
  },

  async clearDocs() {
    if (!confirm("确认清空所有模块的已生成文档？")) return;
    try {
      await API.clearDocs();
      await this.reloadModulesAndDocs();
      UI.toast("已清空文档", "success");
    } catch (err) { UI.toast(err.message, "error"); }
  },
};
