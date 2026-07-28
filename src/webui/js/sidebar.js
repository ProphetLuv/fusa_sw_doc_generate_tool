/* ==================================================================
   sidebar.js — 配置面板（LLM 连接 / ASIL / 模块名 / Key 池 / 模板）
   ================================================================== */

const Sidebar = {
  el() { return document.getElementById("sidebar-body"); },
  tplAgent: AGENT_ORDER[0],       // 模板区当前选中的 Agent（跨重渲染保留）

  render() {
    const c = Store.config;
    const provider = c.provider || "openai";
    const modelPh = Store.defaultModels[provider] || "gpt-4o";
    const basePh = Store.providerBaseUrls[provider] || "https://api.openai.com/v1";
    const asil = c.asil_level || "ASIL B";
    const temp = (c.temperature != null) ? c.temperature : ASIL_TEMP[asil];
    const keys = c.api_keys || [];
    const tplAgent = this.tplAgent || AGENT_ORDER[0];
    const tplChars = Store.templates[tplAgent] || 0;
    const thinkingEnabled = c.thinking_enabled === true;
    const thinkingIntensity = c.thinking_intensity || 5;

    this.el().innerHTML = `
      <div class="sidebar-section">
        <label class="section-label">🔌 LLM 供应商</label>
        <select class="form-select form-select-sm" id="cfg-provider">
          ${PROVIDERS.map((p) => `<option value="${p}" ${p === provider ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </div>

      <div class="sidebar-section">
        <label class="section-label">🔑 API Key</label>
        <input type="password" class="form-control form-control-sm" id="cfg-apikey"
               value="${UI.esc(c.api_key || "")}" placeholder="sk-..." autocomplete="off" />
        <div class="form-text small">仅存于后端内存，不落盘</div>
      </div>

      <div class="sidebar-section">
        <label class="section-label">🧠 模型名称</label>
        <input type="text" class="form-control form-control-sm" id="cfg-model"
               value="${UI.esc(c.model || "")}" placeholder="${modelPh}" />
      </div>

      <div class="sidebar-section">
        <label class="section-label">🌐 API Base（可选）</label>
        <input type="text" class="form-control form-control-sm" id="cfg-apibase"
               value="${UI.esc(c.api_base || "")}" placeholder="${basePh}" />
      </div>

      <div class="sidebar-section">
        <label class="section-label">⚡ 并发 Key 池（分段并发轮转，每行一个）</label>
        <textarea class="form-control form-control-sm" id="cfg-keys" rows="3"
                  placeholder="每行一个 API Key">${UI.esc(keys.join("\n"))}</textarea>
      </div>

      <hr/>

      <div class="sidebar-section">
        <label class="section-label">🎯 目标模块名（默认）</label>
        <input type="text" class="form-control form-control-sm" id="cfg-modname"
               value="${UI.esc(c.module_name || "目标模块")}" />
      </div>

      <div class="sidebar-section">
        <label class="section-label">🛡️ ASIL 等级</label>
        <select class="form-select form-select-sm" id="cfg-asil">
          ${ASIL_LEVELS.map((a) => `<option value="${a}" ${a === asil ? "selected" : ""}>${a}</option>`).join("")}
        </select>
      </div>

      <div class="sidebar-section">
        <label class="section-label">🌡️ Temperature <span id="temp-val" class="token-tag">${temp}</span></label>
        <input type="range" class="form-range" id="cfg-temp" min="0" max="1" step="0.05" value="${temp}" />
        <div class="form-text small" id="temp-hint">${ASIL_TEMP_HINT[asil] || ""}</div>
      </div>

      <hr/>

      <div class="sidebar-section">
        <label class="section-label">🧠 思考模式 <span class="text-muted small">(实验性)</span></label>
        <div class="form-check form-switch">
          <input class="form-check-input" type="checkbox" id="cfg-thinking" ${thinkingEnabled ? "checked" : ""}>
          <label class="form-check-label small" for="cfg-thinking">启用深度推理</label>
        </div>
        <div class="mt-2">
          <label class="form-label small mb-0">强度 <span id="thinking-val" class="token-tag">${thinkingIntensity}</span></label>
          <input type="range" class="form-range" id="cfg-thinking-intensity"
                 min="1" max="10" step="1" value="${thinkingIntensity}"
                 ${thinkingEnabled ? "" : "disabled"}>
        </div>
        <div class="form-text small" id="thinking-hint">
          ${thinkingIntensity <= 3 ? "轻度 · DeepSeek 自动映射为 high" : thinkingIntensity <= 7 ? "中度 · DeepSeek 自动映射为 high" : "深度 · 充分推理"}
        </div>
        <div class="form-text small text-muted">
          支持：DeepSeek V4 / 千问 Qwen / OpenAI o1-o3 / Claude 3.5+<br>DeepSeek 思考模式下 temperature/top_p 不生效
        </div>
      </div>

      <hr/>

      <div class="sidebar-section">
        <label class="section-label">💾 配置导入 / 导出</label>
        <div class="d-flex gap-2">
          <label class="btn btn-outline-secondary btn-sm flex-fill mb-0">
            导入 JSON
            <input type="file" id="cfg-import" accept=".json" hidden />
          </label>
          <button class="btn btn-outline-secondary btn-sm flex-fill" id="cfg-export">导出 JSON</button>
        </div>
      </div>

      <div class="sidebar-section">
        <label class="section-label">📎 Agent 模板（可选）</label>
        <select class="form-select form-select-sm mb-2" id="tpl-agent">
          ${AGENT_ORDER.map((a) => `<option value="${a}" ${a === tplAgent ? "selected" : ""}>${a}${Store.templates[a] ? " ✓" : ""}</option>`).join("")}
        </select>
        <div class="d-flex gap-2">
          <button class="btn btn-outline-secondary btn-sm flex-fill mb-1" id="tpl-local" type="button">从本地导入（建议）</button>
          <label class="btn btn-outline-secondary btn-sm flex-fill mb-1">
            <span id="tpl-upload-text">${tplChars ? "重新上传模板" : "上传模板文件"}</span>
            <input type="file" id="tpl-file" accept=".md,.txt,.text,.rst,.docx,.xlsx" hidden />
          </label>
        </div>
        <div class="small ${tplChars ? "text-success" : "text-muted"}" id="tpl-status">
          ${tplChars
            ? `<i class="bi bi-check-circle-fill"></i> ${tplAgent} 模板已加载（${tplChars.toLocaleString()} 字符）<button type="button" class="btn btn-link btn-sm p-0 ms-1 align-baseline text-danger" id="tpl-remove">移除</button>`
            : `${tplAgent} 暂无模板 · 支持 .md/.txt/.rst/.docx/.xlsx`}
        </div>
      </div>
    `;
    this.bind();
  },

  bind() {
    const $ = (id) => document.getElementById(id);

    // 供应商切换 → 更新占位符
    $("cfg-provider").addEventListener("change", (e) => {
      Store.config.provider = e.target.value;
      this.saveConfig({ provider: e.target.value });
      this.render();
    });

    // 文本类字段失焦保存
    const bindBlur = (id, key) => {
      $(id).addEventListener("change", (e) => {
        const v = e.target.value.trim();
        Store.config[key] = v || (key === "api_base" ? null : "");
        this.saveConfig({ [key]: Store.config[key] });
      });
    };
    bindBlur("cfg-apikey", "api_key");
    bindBlur("cfg-model", "model");
    bindBlur("cfg-apibase", "api_base");
    bindBlur("cfg-modname", "module_name");

    // Key 池
    $("cfg-keys").addEventListener("change", (e) => {
      const arr = e.target.value.split("\n").map((s) => s.trim()).filter(Boolean);
      Store.config.api_keys = arr;
      this.saveConfig({ api_keys: arr });
    });

    // ASIL → Temperature 联动
    $("cfg-asil").addEventListener("change", (e) => {
      const asil = e.target.value;
      const t = ASIL_TEMP[asil];
      Store.config.asil_level = asil;
      Store.config.temperature = t;
      $("cfg-temp").value = t;
      $("temp-val").textContent = t;
      $("temp-hint").textContent = ASIL_TEMP_HINT[asil] || "";
      this.saveConfig({ asil_level: asil, temperature: t });
    });

    // Temperature 手动调整
    $("cfg-temp").addEventListener("input", (e) => {
      $("temp-val").textContent = e.target.value;
    });
    $("cfg-temp").addEventListener("change", (e) => {
      const t = parseFloat(e.target.value);
      Store.config.temperature = t;
      this.saveConfig({ temperature: t });
    });

    // 思考模式开关
    $("cfg-thinking").addEventListener("change", (e) => {
      const on = e.target.checked;
      Store.config.thinking_enabled = on;
      const slider = $("cfg-thinking-intensity");
      slider.disabled = !on;
      this.saveConfig({ thinking_enabled: on });
    });

    // 思考强度滑块
    $("cfg-thinking-intensity").addEventListener("input", (e) => {
      const v = parseInt(e.target.value);
      $("thinking-val").textContent = v;
      const hint = $("thinking-hint");
      hint.textContent = v <= 3 ? "轻度 · DeepSeek 自动映射为 high" : v <= 7 ? "中度 · DeepSeek 自动映射为 high" : "深度 · 充分推理";
    });
    $("cfg-thinking-intensity").addEventListener("change", (e) => {
      const v = parseInt(e.target.value);
      Store.config.thinking_intensity = v;
      this.saveConfig({ thinking_intensity: v });
    });

    // 导入配置
    $("cfg-import").addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      try {
        const r = await API.importConfig(f);
        Store.config = r.config;
        this.render();
        UI.toast("配置导入成功", "success");
      } catch (err) { UI.toast("导入失败: " + err.message, "error"); }
      e.target.value = "";
    });

    // 导出配置
    $("cfg-export").addEventListener("click", () => {
      UI.download("/api/config/export", "llm_config.json");
    });

    // 模板：切换 Agent → 刷新该 Agent 的模板状态显示
    $("tpl-agent").addEventListener("change", (e) => {
      this.tplAgent = e.target.value;
      this.render();
    });

    // 模板上传（含解析中状态 + 超时控制 + 文件大小提示 + 连接预检）
    $("tpl-file").addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) return;

      // 前端文件大小预检（>50MB 直接拒绝，避免无意义的上传）
      const MAX_SIZE = 50 * 1024 * 1024;
      if (f.size > MAX_SIZE) {
        const st = $("tpl-status");
        st.className = "small text-danger";
        st.innerHTML = `<i class="bi bi-x-circle-fill"></i> 文件过大（${(f.size / 1024 / 1024).toFixed(1)} MB），上限 50 MB`;
        UI.toast("模板文件过大，请压缩后上传", "error");
        e.target.value = "";
        return;
      }

      const agent = $("tpl-agent").value;
      this.tplAgent = agent;
      const st = $("tpl-status");
      const txt = $("tpl-upload-text");
      const sizeStr = f.size > 1024 * 1024
        ? `${(f.size / 1024 / 1024).toFixed(1)} MB`
        : `${(f.size / 1024).toFixed(0)} KB`;
      if (txt) txt.textContent = "解析中…";
      st.className = "small text-muted";
      st.innerHTML = `<span class="spinner-border spinner-border-sm" role="status"></span> 正在解析 ${UI.esc(f.name)}（${sizeStr}）…`;

      // AbortController 超时控制（120 秒，大文件 Word 解析可能较慢）
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 120000);
      try {
        const r = await API.uploadTemplate(agent, f, ctrl.signal);
        clearTimeout(timer);
        Store.templates[agent] = r.chars;
        UI.toast(`${agent} 模板已加载（${r.chars.toLocaleString()} 字符）`, "success");
        this.render();
      } catch (err) {
        clearTimeout(timer);
        if (txt) txt.textContent = "上传模板文件";
        st.className = "small text-danger";
        let msg;
        if (err.name === "AbortError") {
          msg = "解析超时，请尝试压缩文件或拆分后上传";
        } else if (err.message && err.message.includes("Failed to fetch")) {
          msg = "无法连接服务器，请确认服务已启动后刷新页面";
        } else {
          msg = UI.esc(err.message || "未知错误");
        }
        st.innerHTML = `<i class="bi bi-x-circle-fill"></i> 解析失败：${msg}`;
        UI.toast("模板解析失败: " + msg, "error");
      }
      e.target.value = "";
    });

    // 模板：从本地路径导入（绕过浏览器上传，避免安全软件拦截）
    $("tpl-local").addEventListener("click", async () => {
      const agent = this.tplAgent || $("tpl-agent").value;
      const st = $("tpl-status");
      const txt = $("tpl-upload-text");

      // 第一步：弹出本地文件选择对话框
      st.className = "small text-muted";
      st.innerHTML = `<span class="spinner-border spinner-border-sm" role="status"></span> 正在打开文件选择对话框…`;
      try {
        const pick = await API.pickTemplatePath();
        if (!pick.path) {
          // 用户取消了选择
          st.className = "small text-muted";
          const tplChars = Store.templates[agent] || 0;
          st.innerHTML = tplChars
            ? `<i class="bi bi-check-circle-fill"></i> ${agent} 模板已加载（${tplChars.toLocaleString()} 字符）<button type="button" class="btn btn-link btn-sm p-0 ms-1 align-baseline text-danger" id="tpl-remove">移除</button>`
            : `${agent} 暂无模板 · 支持 .md/.txt/.rst/.docx/.xlsx`;
          return;
        }

        // 第二步：通知服务端从本地路径读取并解析文件
        if (txt) txt.textContent = "解析中…";
        st.className = "small text-muted";
        const fn = pick.path.replace(/\\/g, "/").split("/").pop();
        st.innerHTML = `<span class="spinner-border spinner-border-sm" role="status"></span> 正在解析 ${UI.esc(fn)}…`;

        const r = await API.uploadTemplateLocalPath(agent, pick.path);
        Store.templates[agent] = r.chars;
        UI.toast(`${agent} 模板已加载（${r.chars.toLocaleString()} 字符，${r.filename || fn}）`, "success");
        this.render();
      } catch (err) {
        if (txt) txt.textContent = "上传模板文件";
        st.className = "small text-danger";
        let msg;
        if (err.message && err.message.includes("Failed to fetch")) {
          msg = "无法连接服务器，请确认服务已启动后刷新页面";
        } else {
          msg = UI.esc(err.message || "未知错误");
        }
        st.innerHTML = `<i class="bi bi-x-circle-fill"></i> 导入失败：${msg}`;
        UI.toast("模板导入失败: " + msg, "error");
      }
    });

    // 移除已加载模板
    const rm = $("tpl-remove");
    if (rm) rm.addEventListener("click", async () => {
      const agent = this.tplAgent || $("tpl-agent").value;
      try {
        await API.deleteTemplate(agent);
        delete Store.templates[agent];
        UI.toast(`${agent} 模板已移除`, "info");
        this.render();
      } catch (err) { UI.toast("移除失败: " + err.message, "error"); }
    });
  },

  async saveConfig(patch) {
    try {
      const r = await API.updateConfig(patch);
      Store.config = r.config;
    } catch (err) { UI.toast("配置保存失败: " + err.message, "error"); }
  },
};
