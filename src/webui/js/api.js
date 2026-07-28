/* ==================================================================
   api.js — REST 封装 + SSE 封装 + 全局 UI 辅助
   ================================================================== */

const API = {
  async _json(method, url, body, isForm, signal) {
    const opts = { method, headers: {}, cache: "no-store" };
    if (signal) opts.signal = signal;
    if (body !== undefined) {
      if (isForm) {
        opts.body = body; // FormData
      } else {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = j.detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  },
  get(url) { return this._json("GET", url); },
  put(url, body) { return this._json("PUT", url, body); },
  post(url, body) { return this._json("POST", url, body); },
  del(url, body) { return this._json("DELETE", url, body); },
  postForm(url, formData, signal) { return this._json("POST", url, formData, true, signal); },

  // ---- 配置 ----
  getConfig() { return this.get("/api/config"); },
  updateConfig(patch) { return this.put("/api/config", patch); },
  importConfig(file) { const fd = new FormData(); fd.append("file", file); return this.postForm("/api/config/import", fd); },

  // ---- 上传 ----
  uploadFiles(files) {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return this.postForm("/api/upload/files", fd);
  },
  uploadZip(file) { const fd = new FormData(); fd.append("file", file); return this.postForm("/api/upload/zip", fd); },
  uploadLocalPath(path) { return this.post("/api/upload/local-path", { path }); },
  uploadPaste(code, module_name) { return this.post("/api/upload/paste", { code, module_name }); },
  pickLocalPath(mode) { return this.get(`/api/upload/pick?mode=${mode}`); },
  clearUpload() { return this.del("/api/upload"); },

  // ---- 模块 ----
  listModules() { return this.get("/api/modules"); },
  mergeModules(names, new_name) { return this.post("/api/modules/merge", { names, new_name }); },
  renameModule(old_name, new_name) { return this.post("/api/modules/rename", { old_name, new_name }); },
  deleteModule(name) { return this.post("/api/modules/delete", { name }); },
  setActiveModule(module) { return this.put("/api/modules/active", { module }); },
  setSelectedModules(modules) { return this.put("/api/modules/selected", { modules }); },
  getModuleCode(name) { return this.get(`/api/modules/${encodeURIComponent(name)}/code`); },
  getModuleAnalysis(name) { return this.get(`/api/modules/${encodeURIComponent(name)}/analysis`); },

  // ---- 预估 ----
  estimateAgent(agent, module, chunked, review) {
    const q = new URLSearchParams();
    q.set("_t", Date.now());
    if (module) q.set("module", module);
    if (chunked) q.set("chunked", "true");
    if (review) q.set("review", "true");
    return this.get(`/api/estimate/agent/${agent}?${q}`);
  },
  estimateBatch(module) {
    const q = new URLSearchParams();
    q.set("_t", Date.now());
    if (module) q.set("module", module);
    return this.get(`/api/estimate/batch?${q}`);
  },

  // ---- 文档 ----
  listDocs(module) { const q = module ? `?module=${encodeURIComponent(module)}` : ""; return this.get(`/api/docs${q}`); },
  getDoc(module, agent) { return this.get(`/api/docs/${encodeURIComponent(module)}/${agent}`); },
  deleteDoc(module, agent) { return this.del(`/api/docs/${encodeURIComponent(module)}/${agent}`); },
  clearDocs() { return this.del("/api/docs"); },
  crossValidate(module) { return this.post("/api/validate/cross", { module }); },
  getHistory(limit) { return this.get(`/api/history?limit=${limit || 50}`); },

  // ---- 模板 ----
  listTemplates() { return this.get("/api/templates"); },
  uploadTemplate(agent, file, signal) { const fd = new FormData(); fd.append("file", file); return this.postForm(`/api/templates/${agent}`, fd, signal); },
  uploadTemplateLocalPath(agent, path) { return this.post(`/api/templates/${agent}/local-path`, { path }); },
  pickTemplatePath() { return this.get("/api/templates/pick"); },
  deleteTemplate(agent) { return this.del(`/api/templates/${agent}`); },

  // ---- 生成取消 ----
  cancelGeneration() { return this.post("/api/generate/cancel"); },

  // ---- 导出（返回下载） ----
  downloadUrl(kind, params) {
    const q = new URLSearchParams(params || {});
    return `/api/export/${kind}?${q}`;
  },
};

/* ------------------------------------------------------------------
   SSE：EventSource 封装（GET）
   参数 handlers: { token, status, progress, chunk_init, merge_start,
                    done, batch_done, error, open }
   返回 EventSource（可 .close() 取消）
   ------------------------------------------------------------------ */
function openSSE(url, handlers) {
  const es = new EventSource(url);
  const bind = (name) => {
    es.addEventListener(name, (e) => {
      let data = {};
      try { data = JSON.parse(e.data); } catch (_) {}
      if (handlers[name]) handlers[name](data);
    });
  };
  ["token", "status", "progress", "chunk_init", "merge_start", "done", "batch_done", "error"].forEach(bind);
  es.onopen = () => { if (handlers.open) handlers.open(); };
  es.onerror = () => {
    // EventSource 在流正常结束后也会触发 error；由业务层用 done/batch_done 判定结束并 close
    if (handlers._neterror) handlers._neterror();
  };
  return es;
}

/* ------------------------------------------------------------------
   全局 UI 辅助：Toast / 遮罩 / 文件下载
   ------------------------------------------------------------------ */
const UI = {
  toast(msg, type = "info") {
    const map = { info: "text-bg-primary", success: "text-bg-success", warn: "text-bg-warning", error: "text-bg-danger" };
    const el = document.createElement("div");
    el.className = `toast align-items-center border-0 ${map[type] || map.info}`;
    el.setAttribute("role", "alert");
    el.innerHTML = `<div class="d-flex"><div class="toast-body">${msg}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
    document.getElementById("toast-container").appendChild(el);
    const t = new bootstrap.Toast(el, { delay: type === "error" ? 6000 : 3000 });
    t.show();
    el.addEventListener("hidden.bs.toast", () => el.remove());
  },
  overlay(show, text) {
    const ov = document.getElementById("global-overlay");
    if (text) document.getElementById("overlay-text").textContent = text;
    ov.classList.toggle("d-none", !show);
  },
  download(url, filename) {
    const a = document.createElement("a");
    a.href = url;
    if (filename) a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  },
  esc(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },
};

/* Markdown 渲染（marked + highlight.js） */
function renderMarkdown(el, text) {
  if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true });
    el.innerHTML = marked.parse(text || "");
    if (window.hljs) el.querySelectorAll("pre code").forEach((b) => hljs.highlightElement(b));
  } else {
    el.textContent = text || "";
  }
}
