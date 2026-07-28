/* ==================================================================
   sidebar.js — 配置面板（LLM 连接 / ASIL / 模块名 / Key 池 / 模板）
   ================================================================== */

const Sidebar = {
  el() { return document.getElementById("sidebar-body"); },

  render() {
    const c = Store.config;
    const provider = c.provider || "openai";
    const modelPh = Store.defaultModels[provider] || "gpt-4o";
    const basePh = Store.providerBaseUrls[provider] || "https://api.openai.com/v1";
    const asil = c.asil_level || "ASIL B";
    const temp = (c.temperature != null) ? c.temperature : ASIL_TEMP[asil];
    const keys = c.api_keys || [];

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
          ${AGENT_ORDER.map((a) => `<option value="${a}">${a}${Store.templates[a] ? " ✓" : ""}</option>`).join("")}
        </select>
        <label class="btn btn-outline-secondary btn-sm w-100 mb-0">
          上传模板文件
          <input type="file" id="tpl-file" hidden />
        </label>
        <div class="form-text small" id="tpl-status"></div>
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

    // 模板上传
    $("tpl-file").addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      const agent = $("tpl-agent").value;
      try {
        const r = await API.uploadTemplate(agent, f);
        Store.templates[agent] = r.chars;
        $("tpl-status").textContent = `${agent} 模板已加载（${r.chars} 字符）`;
        this.render();
        UI.toast(`${agent} 模板已加载`, "success");
      } catch (err) { UI.toast("模板解析失败: " + err.message, "error"); }
      e.target.value = "";
    });
  },

  async saveConfig(patch) {
    try {
      const r = await API.updateConfig(patch);
      Store.config = r.config;
    } catch (err) { UI.toast("配置保存失败: " + err.message, "error"); }
  },
};
