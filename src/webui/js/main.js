/* ==================================================================
   main.js — 路由与初始化
   ================================================================== */

/* 根据系统配色同步 Bootstrap 主题与代码高亮主题，避免暗色下深字深底不可读 */
function applyColorScheme() {
  const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-bs-theme", dark ? "dark" : "light");
  const hljsLink = document.getElementById("hljs-theme");
  if (hljsLink) {
    hljsLink.href = dark
      ? "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/styles/github-dark.min.css"
      : "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/styles/github.min.css";
  }
}
applyColorScheme();
if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyColorScheme);
}

const Router = {
  go(view) {
    if (Store.generating && view !== Store.view) {
      // 允许切换视图，但提示后台任务仍在进行
    }
    Store.view = view;
    document.querySelectorAll("#view-tabs button").forEach((b) =>
      b.classList.toggle("active", b.dataset.view === view));
    document.getElementById("view-dashboard").classList.toggle("d-none", view !== "dashboard");
    document.getElementById("view-workspace").classList.toggle("d-none", view !== "workspace");
    if (view === "dashboard") Dashboard.render();
    else Workspace.render();
  },
};

async function bootstrapApp() {
  // 绑定视图切换
  document.querySelectorAll("#view-tabs button").forEach((b) =>
    b.addEventListener("click", () => Router.go(b.dataset.view)));

  // 拉取配置
  try {
    const cfg = await API.getConfig();
    Store.config = cfg.config || {};
    Store.providerBaseUrls = cfg.provider_base_urls || {};
    Store.defaultModels = cfg.default_models || {};
  } catch (err) {
    UI.toast("配置加载失败: " + err.message, "error");
  }

  // 拉取模块快照 + 模板 + 文档概览
  try {
    const snap = await API.listModules();
    Store.applyModulesSnapshot(snap);
  } catch (err) { /* ignore */ }

  try {
    const tpl = await API.listTemplates();
    Store.templates = tpl.templates || {};
  } catch (err) { /* ignore */ }

  try {
    const docs = await API.listDocs(Store.activeModule);
    Store.docsOverview = docs.overview || {};
    Store.activeModuleDocs = (docs.docs || []).map((d) => d.agent);
  } catch (err) { /* ignore */ }

  // 首屏渲染
  Sidebar.render();
  Router.go("dashboard");

  // 头部状态：模块数
  Store.on("modules", () => {
    const s = document.getElementById("header-status");
    if (s) s.textContent = Store.modules.length
      ? `${Store.modules.length} 模块 · 活动：${Store.activeModule || "-"}`
      : "未加载代码";
  });
  Store.emit("modules");
}

document.addEventListener("DOMContentLoaded", bootstrapApp);
