/* ==================================================================
   workspace.js — 单文档工作台
   Agent 选择 · 前置文档提示 · 生成选项（分段/审查/长度）· Token 预估
   · SSE 流式生成 · Markdown 渲染 · 质量校验 · 版本 Diff · 下载 · 历史
   ================================================================== */

const Workspace = {
  el() { return document.getElementById("view-workspace"); },
  _sse: null,
  _fullText: "",
  _chunkBuffers: {},

  render() {
    const agent = Store.wsAgent;
    const m = AGENT_META[agent];
    const mod = Store.activeModule || Store.defaultModuleName;
    this.el().innerHTML = `
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h1 class="main-title" style="font-size:1.6rem;text-align:left;margin:0">
          ${m.icon} ${m.name} <small class="text-muted fs-6">${m.full}</small>
        </h1>
      </div>

      <div class="row g-3">
        <!-- 左：控制 -->
        <div class="col-lg-4">
          <div class="card mb-2"><div class="card-body">
            <label class="section-label">选择 Agent</label>
            <select class="form-select form-select-sm mb-3" id="ws-agent">
              ${AGENT_ORDER.map((a) => `<option value="${a}" ${a === agent ? "selected" : ""}>${AGENT_META[a].icon} ${a} · ${AGENT_META[a].full}</option>`).join("")}
            </select>

            <label class="section-label">活动模块</label>
            <div class="mb-3"><span class="badge text-bg-primary">${UI.esc(mod)}</span>
              ${Store.hasCode ? "" : '<span class="text-danger small">（无代码）</span>'}</div>

            <div id="prior-hint" class="mb-3"></div>

            <label class="section-label">生成选项</label>
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="ws-chunked">
              <label class="form-check-label small" for="ws-chunked">分段并发生成（长文档更快，需多 Key 更佳）</label>
            </div>
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="ws-review">
              <label class="form-check-label small" for="ws-review">生成后自动审查修订</label>
            </div>

            <label class="section-label mt-3">最大输出 Token（可选）</label>
            <input type="number" class="form-control form-control-sm" id="ws-maxtokens" placeholder="留空用 ASIL 推荐值" min="1024" step="1024">

            <div id="ws-est" class="small text-muted mt-3"></div>

            <div class="d-grid gap-2 mt-3">
              <button class="btn btn-primary" id="ws-generate">✨ 生成文档</button>
              <button class="btn btn-danger d-none" id="ws-stop">⏹ 停止</button>
            </div>
          </div></div>

          <div class="card"><div class="card-body">
            <label class="section-label">📜 生成历史</label>
            <div id="ws-history" class="small"></div>
          </div></div>
        </div>

        <!-- 右：结果 -->
        <div class="col-lg-8">
          <div class="card"><div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <ul class="nav nav-tabs card-header-tabs" id="ws-result-tabs">
                <li class="nav-item"><button class="nav-link active" data-rtab="doc">文档</button></li>
                <li class="nav-item"><button class="nav-link" data-rtab="check">质量校验</button></li>
                <li class="nav-item"><button class="nav-link" data-rtab="diff">版本 Diff</button></li>
              </ul>
              <div class="btn-group btn-group-sm" id="ws-downloads"></div>
            </div>
            <div id="ws-status" class="small text-muted mb-2"></div>
            <div id="ws-rpane-doc"><div class="doc-render" id="ws-doc"><span class="text-muted">尚无内容，点击「生成文档」。</span></div></div>
            <div id="ws-rpane-check" class="d-none"></div>
            <div id="ws-rpane-diff" class="d-none"></div>
          </div></div>
        </div>
      </div>
    `;
    this.bind();
    this.renderPriorHint();
    this.refreshEstimate();
    this.loadExistingDoc();
    this.loadHistory();
  },

  bind() {
    const $ = (id) => document.getElementById(id);
    $("ws-agent").addEventListener("change", (e) => { Store.wsAgent = e.target.value; this.render(); });
    $("ws-chunked").addEventListener("change", () => this.refreshEstimate());
    $("ws-review").addEventListener("change", () => this.refreshEstimate());
    $("ws-generate").addEventListener("click", () => this.generate());
    $("ws-stop").addEventListener("click", () => this.stop());
    this.el().querySelectorAll("#ws-result-tabs button").forEach((b) =>
      b.addEventListener("click", () => this.switchTab(b.dataset.rtab)));
  },

  switchTab(tab) {
    this.el().querySelectorAll("#ws-result-tabs button").forEach((b) =>
      b.classList.toggle("active", b.dataset.rtab === tab));
    ["doc", "check", "diff"].forEach((t) =>
      document.getElementById(`ws-rpane-${t}`).classList.toggle("d-none", t !== tab));
  },

  renderPriorHint() {
    const box = document.getElementById("prior-hint");
    const prior = {
      "FMEA": ["SRS", "SAD"], "DFA": ["SAD", "FMEA", "SRS"],
      "TC-UNIT": ["SRS", "SAD", "FMEA", "DFA"], "TC-INTEGRATION": ["SRS", "SAD", "FMEA", "DFA"],
    }[Store.wsAgent];
    if (!prior) { box.innerHTML = ""; return; }
    box.innerHTML = `<div class="alert alert-info small mb-0 py-2">
      💡 本 Agent 会自动注入前置文档：<b>${prior.join(" · ")}</b>（若已生成）。建议先完成这些文档以提高质量。</div>`;
  },

  async refreshEstimate() {
    const box = document.getElementById("ws-est");
    if (!box) return;
    const chunked = document.getElementById("ws-chunked").checked;
    const review = document.getElementById("ws-review").checked;
    try {
      const r = await API.estimateAgent(Store.wsAgent, Store.activeModule, chunked, review);
      box.innerHTML = `
        <table class="est-table w-100">
          <tr><td>源代码</td><td>${r.code_tokens.toLocaleString()}</td></tr>
          <tr><td>模板 + 知识库</td><td>${(r.template_tokens + r.knowledge_tokens).toLocaleString()}</td></tr>
          <tr><td>前置文档注入</td><td>${r.prior_docs_tokens.toLocaleString()}</td></tr>
          <tr><td>预计输出</td><td>${r.output_estimated.toLocaleString()}</td></tr>
          <tr><td>调用轮次</td><td>${r.call_rounds}</td></tr>
          <tr class="fw-bold"><td>合计</td><td>${r.grand_total.toLocaleString()} tok</td></tr>
          <tr><td>预计成本</td><td>${r.cost || "-"}</td></tr>
        </table>
        <div class="form-text">默认最大输出：${r.default_max_tokens} tok</div>`;
      if (!document.getElementById("ws-maxtokens").value)
        document.getElementById("ws-maxtokens").placeholder = `默认 ${r.default_max_tokens}`;
    } catch (err) { box.textContent = "预估不可用: " + err.message; }
  },

  /* ---------------- 加载已有文档 / 历史 ---------------- */
  async loadExistingDoc() {
    if (!Store.activeModule) return;
    try {
      const r = await API.getDoc(Store.activeModule, Store.wsAgent);
      this._fullText = r.content;
      renderMarkdown(document.getElementById("ws-doc"), r.content);
      this.renderCheck(r.validation);
      this.renderDiff(r.diff, r.version_count);
      this.renderDownloads(r.token_usage);
    } catch (err) {
      // 404 = 尚未生成，忽略
      this.renderDownloads(null);
    }
  },

  async loadHistory() {
    const box = document.getElementById("ws-history");
    try {
      const r = await API.getHistory(20);
      const items = (r.history || []).filter((h) => !Store.activeModule || h.module === Store.activeModule);
      if (!items.length) { box.innerHTML = '<span class="text-muted">暂无记录</span>'; return; }
      box.innerHTML = items.slice(0, 15).map((h) => {
        const ok = h.status.includes("成功");
        return `<div class="d-flex justify-content-between border-bottom py-1">
          <span>${ok ? "✅" : "❌"} ${UI.esc(h.doc_type)}</span>
          <span class="text-muted">${UI.esc(h.timestamp.slice(5, 16))}</span></div>`;
      }).join("");
    } catch (err) { box.innerHTML = '<span class="text-danger">加载失败</span>'; }
  },

  /* ---------------- 生成（SSE） ---------------- */
  generate() {
    if (!Store.config.api_key) { UI.toast("请先在左侧配置 API Key", "warn"); return; }
    if (!Store.hasCode) { UI.toast("当前模块无代码", "warn"); return; }
    if (Store.generating) { UI.toast("已有生成任务在进行", "warn"); return; }

    Store.generating = true;
    this._fullText = "";
    this._chunkBuffers = {};
    document.getElementById("ws-generate").classList.add("d-none");
    document.getElementById("ws-stop").classList.remove("d-none");
    this.switchTab("doc");
    const docEl = document.getElementById("ws-doc");
    docEl.innerHTML = "";
    docEl.classList.add("stream-cursor");
    const st = document.getElementById("ws-status");

    const chunked = document.getElementById("ws-chunked").checked;
    const review = document.getElementById("ws-review").checked;
    const maxTokens = document.getElementById("ws-maxtokens").value;

    const q = new URLSearchParams();
    if (Store.activeModule) q.set("module", Store.activeModule);
    if (chunked) q.set("chunked", "true");
    if (review) q.set("review", "true");
    if (maxTokens) q.set("max_tokens", maxTokens);
    // 审查复用主配置
    if (review) {
      q.set("review_provider", Store.config.provider || "openai");
      q.set("review_api_key", Store.config.api_key || "");
      if (Store.config.api_base) q.set("review_api_base", Store.config.api_base);
      if (Store.config.model) q.set("review_model", Store.config.model);
    }

    let raw = "";  // 非分段模式累积
    this._sse = openSSE(`/api/generate/${Store.wsAgent}/stream?${q}`, {
      status: (d) => { st.textContent = d.message; },
      chunk_init: (d) => {
        st.textContent = `分为 ${d.titles.length} 段并发（${d.keys} Key）`;
        d.titles.forEach((t, i) => { this._chunkBuffers[i] = ""; });
      },
      token: (d) => {
        if (d.phase === "chunk") {
          this._chunkBuffers[d.chunk] = (this._chunkBuffers[d.chunk] || "") + d.text;
          const combined = Object.keys(this._chunkBuffers).sort((a, b) => a - b)
            .map((k) => this._chunkBuffers[k]).join("\n\n");
          renderMarkdown(docEl, combined);
        } else {
          raw += d.text;
          renderMarkdown(docEl, raw);
        }
        docEl.scrollTop = docEl.scrollHeight;
      },
      merge_start: () => { st.textContent = "🔗 一致性合并审查中..."; raw = ""; },
      done: (d) => {
        this._fullText = d.content;
        renderMarkdown(docEl, d.content);
        docEl.classList.remove("stream-cursor");
        st.textContent = `✅ 完成 · ${d.validation.summary}`;
        this.renderCheck(d.validation);
        this.renderDownloads(d.token_usage);
        this.finish();
        this.loadHistory();
        Dashboard.reloadModulesAndDocs();
        UI.toast(`${Store.wsAgent} 生成完成`, "success");
        // 重新拉取以获取 diff/version
        this.loadExistingDoc();
      },
      error: (d) => {
        docEl.classList.remove("stream-cursor");
        st.textContent = "❌ " + d.message;
        UI.toast("生成失败: " + d.message, "error");
        this.finish();
      },
      _neterror: () => { if (Store.generating) { docEl.classList.remove("stream-cursor"); this.finish(); } },
    });
  },

  stop() {
    if (this._sse) { this._sse.close(); this._sse = null; }
    document.getElementById("ws-doc").classList.remove("stream-cursor");
    document.getElementById("ws-status").textContent = "⏹ 已停止（本地中断，后端可能仍在生成）";
    this.finish();
  },

  finish() {
    Store.generating = false;
    if (this._sse) { this._sse.close(); this._sse = null; }
    const g = document.getElementById("ws-generate");
    const s = document.getElementById("ws-stop");
    if (g) g.classList.remove("d-none");
    if (s) s.classList.add("d-none");
  },

  /* ---------------- 校验 / Diff / 下载 ---------------- */
  renderCheck(validation) {
    const box = document.getElementById("ws-rpane-check");
    if (!validation) { box.innerHTML = '<span class="text-muted">暂无校验结果</span>'; return; }
    box.innerHTML = `
      <div class="mb-2">${validation.passed ? '<span class="badge text-bg-success">通过</span>' : '<span class="badge text-bg-warning">存在问题</span>'} ${UI.esc(validation.summary)}</div>
      ${(validation.results || []).map((c) => Dashboard.checkItem(c)).join("")}`;
  },

  renderDiff(diff, versionCount) {
    const box = document.getElementById("ws-rpane-diff");
    if (!diff) { box.innerHTML = `<span class="text-muted">无历史版本可对比（当前版本数：${versionCount || 0}）</span>`; return; }
    const html = diff.split("\n").map((l) => {
      let cls = "";
      if (l.startsWith("+") && !l.startsWith("+++")) cls = "color:#1b5e20;background:#e8f5e9";
      else if (l.startsWith("-") && !l.startsWith("---")) cls = "color:#b71c1c;background:#ffebee";
      else if (l.startsWith("@@")) cls = "color:#4a6fdc";
      return `<div style="${cls}">${UI.esc(l) || "&nbsp;"}</div>`;
    }).join("");
    box.innerHTML = `<pre class="doc-render" style="font-size:0.8rem">${html}</pre>`;
  },

  renderDownloads(tokenUsage) {
    const box = document.getElementById("ws-downloads");
    if (!box) return;
    const hasDoc = !!this._fullText && !this._fullText.startsWith("生成失败");
    if (!hasDoc) { box.innerHTML = ""; return; }
    const mod = Store.activeModule || Store.defaultModuleName;
    const agent = Store.wsAgent;
    let btns = `
      <button class="btn btn-outline-secondary" id="dl-md">MD</button>
      <button class="btn btn-outline-secondary" id="dl-word">Word</button>`;
    if (agent === "FMEA") btns += `<button class="btn btn-outline-secondary" id="dl-excel">Excel</button>`;
    box.innerHTML = btns;
    document.getElementById("dl-md").addEventListener("click", () => {
      const blob = new Blob([this._fullText], { type: "text/markdown" });
      UI.download(URL.createObjectURL(blob), `${mod}_${agent}.md`);
    });
    document.getElementById("dl-word").addEventListener("click", () =>
      UI.download(API.downloadUrl("word", { module: mod, agent }), `${mod}_${agent}.docx`));
    if (agent === "FMEA")
      document.getElementById("dl-excel").addEventListener("click", () =>
        UI.download(API.downloadUrl("excel", { module: mod, agent }), `${mod}_FMEA.xlsx`));

    if (tokenUsage) {
      const st = document.getElementById("ws-status");
      const tag = tokenUsage.is_actual ? "实际" : "估算";
      st.innerHTML += ` <span class="token-tag">${tag} ${tokenUsage.total_tokens.toLocaleString()} tok · ${tokenUsage.duration_sec}s</span>`;
    }
  },
};
