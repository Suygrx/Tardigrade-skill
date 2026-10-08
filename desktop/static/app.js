/* Tardigrade-skill desktop frontend — CC Switch style (dark, topbar, skills management) */
"use strict";

const $ = (sel) => document.querySelector(sel);
let MATRIX = null;
let SETTINGS = { roots: [], download_dir: "" };
let INSTALLED = null;
let LIBRARY = null;
let SELECTED_PLATFORM = localStorage.getItem("tardigrade.platform") || "claude-code";
const MANAGE = { rows: [], platforms: [], filter: null, q: "" };

const TIER_LABEL = {
  "full": ["一键可用", "tier-full"],
  "full*": ["可用需确认", "tier-full-star"],
  "adapted": ["需适配", "tier-adapted"],
  "partial": ["手动步骤", "tier-partial"],
  "incompatible": ["不兼容", "tier-incompatible"],
};

const VIEW_TITLES = { home: "", manage: "Skills 管理", discover: "市场" };

async function api(path, body) {
  const opts = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    let msg = `${resp.status}`;
    try { msg = (await resp.json()).detail || msg; } catch (e) { /* ignore */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return resp.json();
}

function toast(msg, ms = 2600) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), ms);
}

/* 外部浏览器打开（exe 里没有 window.open 可用的目标窗口） */
async function openExternal(url) {
  if (!/^https?:\/\//.test(url)) return;
  try { await api("/api/open-url", { url }); } catch (e) { toast(`打开失败：${e.message}`); }
}

/* markdown 里渲染出来的链接全部走外部浏览器（事件委托） */
document.addEventListener("click", (e) => {
  const a = e.target.closest(".md-link");
  if (a) { e.preventDefault(); openExternal(a.dataset.url); }
});

/* 通用确认弹窗（pywebview 里没有原生 confirm） */
function ask(text) {
  return new Promise((resolve) => {
    $("#confirm-text").textContent = text;
    $("#confirm-mask").classList.remove("hidden");
    $("#confirm-box").classList.remove("hidden");
    const done = (v) => {
      $("#confirm-mask").classList.add("hidden");
      $("#confirm-box").classList.add("hidden");
      $("#confirm-ok").onclick = null;
      $("#confirm-cancel").onclick = null;
      $("#confirm-mask").onclick = null;
      resolve(v);
    };
    $("#confirm-ok").onclick = () => done(true);
    $("#confirm-cancel").onclick = () => done(false);
    $("#confirm-mask").onclick = () => done(false);
  });
}

/* 极简 markdown 渲染（标题/列表/粗体/行内代码/代码块） */
function renderMd(src) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  // inline: code / bold / italic / strikethrough / link
  const inline = (s) =>
    esc(s)
      .replace(/`([^`]+)`/g, '<code class="md-inline">$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>")
      .replace(/~~([^~]+)~~/g, "<s>$1</s>")
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a class="md-link" href="#" data-url="$2" title="$2">$1</a>');

  const lines = src.split("\n");
  const out = [];
  let i = 0;
  // YAML frontmatter -> 渲染为头部元信息
  if (lines[0] && /^---\s*$/.test(lines[0])) {
    const fm = [];
    for (i = 1; i < lines.length && !/^---\s*$/.test(lines[i]); i++) fm.push(lines[i]);
    i++; // skip closing ---
    if (fm.length) {
      out.push('<div class="md-frontmatter">');
      for (const l of fm) {
        const m = l.match(/^(\w[\w-]*):\s*(.*)$/);
        if (m) out.push(`<div class="md-fm-row"><span class="md-fm-k">${esc(m[1])}</span><span class="md-fm-v">${inline(m[2].replace(/^["']|["']$/g, ""))}</span></div>`);
      }
      out.push("</div>");
    }
  }

  let inCode = false, codeLang = "", codeBuf = [], listStack = [];
  const closeLists = () => { while (listStack.length) out.push(listStack.pop() === "ol" ? "</ol>" : "</ul>"); };
  for (; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(/^```\s*(\S*)/);
    if (fence) {
      if (!inCode) { inCode = true; codeLang = fence[1] || ""; codeBuf = []; }
      else { out.push(`<pre class="md-code"${codeLang ? ` data-lang="${esc(codeLang)}"` : ""}><code>${esc(codeBuf.join("\n"))}</code></pre>`); inCode = false; }
      continue;
    }
    if (inCode) { codeBuf.push(line); continue; }
    if (/^<\/pre>$/.test(line)) continue;

    const hm = line.match(/^(#{1,6})\s+(.*)$/);
    if (hm) { closeLists(); out.push(`<h${hm[1].length + 1} class="md-h">${inline(hm[2])}</h${hm[1].length + 1}>`); continue; }
    if (/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(line)) { closeLists(); out.push('<hr class="md-hr">'); continue; }
    const qm = line.match(/^\s*>\s?(.*)$/);
    if (qm) { closeLists(); out.push(`<blockquote class="md-quote">${inline(qm[1])}</blockquote>`); continue; }

    const um = line.match(/^(\s*)[-*+]\s+(.*)$/);
    const om = line.match(/^(\s*)\d+[.)]\s+(.*)$/);
    if (um || om) {
      const type = um ? "ul" : "ol";
      const depth = Math.min(2, Math.floor((um || om)[1].replace(/\t/g, "  ").length / 2));
      while (listStack.length > depth) out.push(listStack.pop() === "ol" ? "</ol>" : "</ul>");
      while (listStack.length <= depth) { out.push(`<${type} class="md-list">`); listStack.push(type); }
      const cur = listStack[listStack.length - 1];
      if (cur !== type) { out.push(listStack.pop() === "ol" ? "</ol>" : "</ul>"); out.push(`<${type} class="md-list">`); listStack.push(type); }
      out.push(`<li>${inline((um || om)[2])}</li>`);
      continue;
    }
    // table: | a | b |
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      closeLists();
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
      i--;
      out.push('<table class="md-table"><thead><tr>' + head.map((h) => `<th>${inline(h)}</th>`).join("") + "</tr></thead><tbody>" +
        rows.map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</tbody></table>");
      continue;
    }
    if (!line.trim()) { closeLists(); out.push('<div class="md-gap"></div>'); continue; }
    closeLists();
    out.push(`<p class="md-p">${inline(line)}</p>`);
  }
  if (inCode) out.push(`<pre class="md-code"><code>${esc(codeBuf.join("\n"))}</code></pre>`);
  closeLists();
  return out.join("");
}

/* ---------------- navigation (topbar) ---------------- */
function setView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
  document.body.dataset.view = name;

  $("#view-title").textContent = VIEW_TITLES[name] || name;
  $("#view-title").classList.toggle("hidden", name === "home");
  $("#btn-back").classList.toggle("hidden", name === "home");
  $("#platform-pill").classList.toggle("hidden", name !== "home");
  $("#btn-manage").classList.toggle("current", name === "manage");
  $("#btn-go-discover").classList.toggle("hidden", name === "discover");

  if (name === "home") loadHome();
  if (name === "manage") loadManage();
  if (name === "discover") populateAgentSelect();
}

document.querySelectorAll("[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

function switchView(name) { setView(name); }

/* ---------------- home (platform cards) ---------------- */
const AGENT_META = {
  "claude-code": { color: "#d97757", short: "Claude" },
  "codex": { color: "#10a37f", short: "Codex" },
  "gemini-cli": { color: "#4285f4", short: "Gemini" },
  "cursor": { color: "#9ca3af", short: "Cursor" },
  "opencode": { color: "#a78bfa", short: "OpenCode" },
  "github-copilot": { color: "#7cb8f8", short: "Copilot" },
  "windsurf": { color: "#2dd4bf", short: "Windsurf" },
  "qwen-code": { color: "#a78bfa", short: "Qwen" },
  "iflow-cli": { color: "#f97316", short: "iFlow" },
  "crush": { color: "#f472b6", short: "Crush" },
  "goose": { color: "#fbbf24", short: "Goose" },
  "droid": { color: "#9ca3af", short: "Droid" },
  "amp": { color: "#e5e7eb", short: "Amp" },
  "cline": { color: "#60a5fa", short: "Cline" },
  "roo": { color: "#f87171", short: "Roo" },
  "kilo": { color: "#34d399", short: "Kilo" },
  "trae": { color: "#ef4444", short: "Trae" },
  "trae-cn": { color: "#dc2626", short: "Trae CN" },
  "workbuddy": { color: "#34d399", short: "WorkBuddy" },
};

function metaOf(agent, fallbackName) {
  return AGENT_META[agent] || { color: "#9ca3af", short: fallbackName || agent };
}

/* 平台 logo（static/logos/<agent>.svg，透明背景；缺失时 img 回退隐藏由 CSS 兜底） */
function logoImg(agent, cls = "") {
  const short = metaOf(agent).short;
  return `<img class="plat-logo ${cls}" src="logos/${agent}.svg" alt="${short}" title="${short}" onerror="this.classList.add('logo-missing')">`;
}

function visiblePlatforms() {
  const detected = INSTALLED.platforms.filter((p) => p.detected);
  return detected.length ? detected : INSTALLED.platforms;
}

function ensureSelectedPlatform() {
  const vis = visiblePlatforms();
  if (!vis.some((p) => p.agent === SELECTED_PLATFORM)) {
    SELECTED_PLATFORM = vis[0]?.agent || "claude-code";
    localStorage.setItem("tardigrade.platform", SELECTED_PLATFORM);
  }
}

function renderPlatformPill() {
  ensureSelectedPlatform();
  const pill = $("#platform-pill");
  pill.innerHTML = visiblePlatforms()
    .map((p) => {
      const meta = metaOf(p.agent, p.name);
      return `<button class="as-btn ${p.agent === SELECTED_PLATFORM ? "active" : ""}" data-platform="${p.agent}" title="${p.name}">
        ${logoImg(p.agent)}${meta.short}
      </button>`;
    })
    .join("");
  pill.querySelectorAll(".as-btn").forEach((b) => {
    b.addEventListener("click", () => {
      SELECTED_PLATFORM = b.dataset.platform;
      localStorage.setItem("tardigrade.platform", SELECTED_PLATFORM);
      renderPlatformPill();
      renderHome();
    });
  });
}

function platformOf(agent) {
  return INSTALLED.platforms.find((p) => p.agent === agent) || { skills: [] };
}

async function loadHome() {
  const box = $("#home-list");
  box.innerHTML = '<div class="loading">加载中…</div>';
  try {
    INSTALLED = await api("/api/installed");
    renderPlatformPill();
    renderHome();
    populateAgentSelect();
  } catch (e) {
    box.innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
  }
}

function populateAgentSelect() {
  if (!INSTALLED) return;
  const sel = $("#discover-agent");
  const current = sel.value;
  sel.innerHTML = INSTALLED.platforms
    .map((p) => `<option value="${p.agent}">${p.name}</option>`)
    .join("");
  if (INSTALLED.platforms.some((p) => p.agent === current)) sel.value = current;
}

function renderHome() {
  const box = $("#home-list");
  const p = platformOf(SELECTED_PLATFORM);
  const meta = metaOf(SELECTED_PLATFORM);
  if (!p.skills.length) {
    box.innerHTML = `<div class="prov-empty">该平台还没有安装任何 skill<br>
      <span style="color:var(--muted-fg);font-size:12px">点右上角 <span style="color:var(--orange)">＋</span> 去「市场」搜索安装，或在「Skills 管理」导入本地 skill</span></div>`;
    return;
  }
  const managedTimes = p.skills.filter((s) => s.managed && s.present).map((s) => s.installed_at || "");
  const latest = managedTimes.length ? Math.max(...managedTimes) : null;

  box.innerHTML = p.skills
    .map((s) => {
      let pill;
      if (!s.present) pill = '<span class="prov-pill pill-missing">缺失</span>';
      else if (!s.managed) pill = '<span class="prov-pill pill-matrix">本机已有</span>';
      else if (String(s.source || "").startsWith("http")) pill = '<span class="prov-pill pill-repo">仓库安装</span>';
      else if (s.source) pill = '<span class="prov-pill pill-repo">本地导入</span>';
      else pill = '<span class="prov-pill pill-matrix">矩阵应用</span>';
      const when = s.installed_at ? s.installed_at.slice(0, 10) : "";
      const status = !s.present
        ? `<span class="prov-err">ⓘ 安装目录不存在</span>`
        : s.managed
          ? `<span class="prov-when">⏱ ${when}</span><span class="prov-ok">✓ 在位</span>`
          : `<span class="prov-when">检测于本机</span>`;
      const state = s.managed && s.present && latest && s.installed_at === latest ? "state-current" : (!s.present ? "state-missing" : "");
      const uninstallBtn = s.managed
        ? `<button class="prov-uninstall" onclick="uninstallSkill('${s.skill}', '${SELECTED_PLATFORM}')">卸载</button>`
        : "";
      return `<div class="prov-card ${state}">
        <span class="prov-grip">⠿</span>
        <div class="prov-avatar">${logoImg(SELECTED_PLATFORM)}</div>
        <div class="prov-main">
          <div class="prov-title-row"><span class="prov-name prov-name-link" data-dir="${s.dest}" title="查看 SKILL.md">${s.skill}</span>${pill}</div>
          <div class="prov-path" title="${s.dest}">${s.dest}</div>
        </div>
        <div class="prov-status">${status}${uninstallBtn}</div>
      </div>`;
    })
    .join("");
  box.querySelectorAll(".prov-name-link").forEach((n) =>
    n.addEventListener("click", () => showSkillMd(n.dataset.dir))
  );
}

async function uninstallSkill(skill, agent) {
  try {
    const r = await api("/api/uninstall", { skill, agent });
    toast(r.ok ? `已卸载：${r.removed}` : r.message);
    loadHome();
  } catch (e) {
    toast(`卸载失败：${e.message}`);
  }
}

$("#btn-go-discover").addEventListener("click", () => switchView("discover"));

/* ---------------- health ---------------- */
async function ping() {
  try {
    const h = await api("/api/health");
    $("#health-badge").textContent = `● 已连接 · v${h.version}`;
  } catch (e) {
    $("#health-badge").textContent = "● 未连接";
  }
  try {
    const s = await api("/api/llm-status");
    $("#llm-badge").textContent = s.configured ? `● 模型已配置 · ${s.model}` : "● BYOK 模型未配置";
    const el = $("#llm-status");
    if (el) {
      el.textContent = s.configured
        ? `已配置：${s.model} @ ${s.base_url}`
        : "未配置。请在下方填写 Base URL / API Key / 模型名（或编辑 ~/.tardigrade/models.toml）。";
      el.className = "llm-status " + (s.configured ? "ok" : "missing");
    }
  } catch (e) { /* ignore */ }
}

/* ---------------- skills 管理（库 + 本机 × 平台开关） ---------------- */
function mgTab(name) {
  document.querySelectorAll(".mg-tab").forEach((t) => t.classList.toggle("active", t.dataset.mg === name));
  document.querySelectorAll(".mg-pane").forEach((p) => p.classList.remove("active"));
  $(`#mg-${name}`).classList.add("active");
  if (name === "skills") loadManage();
  if (name === "matrix") loadMatrix();
  if (name === "pending") loadPending();
  if (name === "settings") loadSettings();
}
document.querySelectorAll(".mg-tab").forEach((t) => t.addEventListener("click", () => mgTab(t.dataset.mg)));

async function loadManage() {
  $("#mg-list").innerHTML = '<div class="loading">加载中…</div>';
  try {
    const [lib, inst] = await Promise.all([api("/api/library"), api("/api/installed")]);
    LIBRARY = lib;
    INSTALLED = inst;
    buildManageRows();
    renderManage();
  } catch (e) {
    $("#mg-list").innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
  }
}

function buildManageRows() {
  const rows = new Map();
  for (const s of LIBRARY.skills) {
    rows.set(s.name, { name: s.name, desc: s.description || "", dir: s.dir, tag: "库", external: false, enabled: {}, externalEnabled: {} });
  }
  for (const p of INSTALLED.platforms) {
    for (const s of p.skills) {
      let row = rows.get(s.skill);
      if (!row) {
        row = { name: s.skill, desc: "", dir: s.dest, tag: s.managed ? "已启用" : "本机", external: !s.managed, enabled: {}, externalEnabled: {} };
        rows.set(s.skill, row);
      }
      if (s.present) {
        row.enabled[p.agent] = true;
        if (!s.managed) row.externalEnabled[p.agent] = true;
      }
      if (!row.desc && !s.managed) row.tag = "本机";
    }
  }
  MANAGE.rows = [...rows.values()].sort((a, b) => a.name.localeCompare(b.name));
  MANAGE.platforms = visiblePlatforms();
}

function renderManage() {
  const chips = $("#mg-chips");
  const counts = {};
  for (const p of MANAGE.platforms) counts[p.agent] = MANAGE.rows.filter((r) => r.enabled[p.agent]).length;
  chips.innerHTML =
    `<button class="mg-chip ${MANAGE.filter === null ? "active" : ""}" data-p="">全部 <span>${MANAGE.rows.length}</span></button>` +
    MANAGE.platforms
      .map((p) => {
        const meta = metaOf(p.agent, p.name);
        return `<button class="mg-chip ${MANAGE.filter === p.agent ? "active" : ""}" data-p="${p.agent}">
          ${logoImg(p.agent, "plat-logo-sm")} ${meta.short} <span>${counts[p.agent] || 0}</span>
        </button>`;
      })
      .join("");
  chips.querySelectorAll(".mg-chip").forEach((c) =>
    c.addEventListener("click", () => { MANAGE.filter = c.dataset.p || null; renderManage(); })
  );

  const q = MANAGE.q.trim().toLowerCase();
  const rows = MANAGE.rows.filter(
    (r) =>
      (!MANAGE.filter || r.enabled[MANAGE.filter]) &&
      (!q || r.name.toLowerCase().includes(q) || (r.desc || "").toLowerCase().includes(q))
  );

  $("#mg-list").innerHTML = rows.length
    ? `<div class="mg-rows">` + rows.map((r) => {
        const icons = MANAGE.platforms
          .map((p) => {
            const meta = metaOf(p.agent, p.name);
            const on = !!r.enabled[p.agent];
            const ext = !!(r.externalEnabled && r.externalEnabled[p.agent]);
            return `<button class="plat-toggle ${on ? "on" : ""}" data-skill="${r.name}" data-agent="${p.agent}"
              title="${meta.short}${on ? "：已开启" : "：未开启"}${ext ? "（本机已有，非 Tardigrade 管理）" : ""}"
              style="--pc:${meta.color}">${logoImg(p.agent)}</button>`;
          })
          .join("");
        return `<div class="mg-row">
          <div class="mg-row-main">
            <div class="prov-title-row"><span class="mg-name" data-dir="${r.dir}" title="查看 SKILL.md">${r.name}</span>
              <span class="prov-pill pill-matrix">${r.tag}</span></div>
            <div class="mg-desc">${(r.desc || "—").slice(0, 120)}</div>
          </div>
          <div class="mg-icons">${icons}${r.tag === "库" ? `<button class="mg-del" data-skill="${r.name}" title="从本地 Skill 库删除">✕</button>` : ""}</div>
        </div>`;
      }).join("") + `</div>`
    : `<div class="prov-empty">没有匹配的 skill</div>`;

  $("#mg-list").querySelectorAll(".plat-toggle").forEach((b) =>
    b.addEventListener("click", () => togglePlatform(b.dataset.skill, b.dataset.agent))
  );
  $("#mg-list").querySelectorAll(".mg-name").forEach((n) =>
    n.addEventListener("click", () => showSkillMd(n.dataset.dir))
  );
  $("#mg-list").querySelectorAll(".mg-del").forEach((b) =>
    b.addEventListener("click", () => deleteLibrarySkill(b.dataset.skill))
  );
}

async function deleteLibrarySkill(name) {
  if (!(await ask(`从本地 Skill 库删除「${name}」？其目录将从下载库中移除（已安装到平台的不受影响，可稍后在各平台手动清理）。`))) return;
  try {
    const r = await api("/api/library/delete", { name });
    toast(r.ok ? `已删除：${name}` : r.message || "删除失败");
    loadManage();
  } catch (e) { toast(`删除失败：${e.message}`); }
}

$("#mg-search").addEventListener("input", (e) => { MANAGE.q = e.target.value; renderManage(); });

async function togglePlatform(skill, agent) {
  const row = MANAGE.rows.find((r) => r.name === skill);
  if (!row) return;
  const pname = metaOf(agent).short;
  if (row.enabled[agent]) {
    if (row.externalEnabled && row.externalEnabled[agent]) return toast("本机已有的 skill，非 Tardigrade 管理，请在该平台手动处理");
    if (!(await ask(`确定在 ${pname} 上关闭（卸载）「${skill}」？`))) return;
    try {
      const r = await api("/api/uninstall", { skill, agent });
      toast(r.ok ? `已卸载：${r.removed}` : r.message);
    } catch (e) { toast(`卸载失败：${e.message}`); }
    loadManage();
    return;
  }
  let r;
  try {
    r = await api("/api/toggle", { dir: row.dir, agent });
  } catch (e) { return toast(`开启失败：${e.message}`); }
  if (r.ok) {
    toast(`已开启：${skill} → ${pname}`);
    loadManage();
    return;
  }
  // 不适配：弹窗询问是否走适配处理
  const [label] = TIER_LABEL[r.tier] || [r.tier];
  if (r.tier === "adapted") {
    const go = await ask(`当前 ${pname} 不适配「${skill}」（${label}），是否要进行适配性处理？`);
    if (!go) return;
    toast("适配中…（调用 BYOK 模型，产物需确认后安装）");
    try {
      const res = await api("/api/adapt", { skill, agent, dir: row.dir });
      toast(res.status === "pending" ? "适配产物已生成，请到「Skills 管理 → 待确认」确认安装" : `适配结果：${res.status}`);
      refreshPendingDot();
    } catch (e) { toast(`适配失败：${e.message}`); }
  } else {
    toast(`当前 ${pname} 不适配「${skill}」（${label}），暂无自动适配方案`);
  }
}

/* skill 详情：读取并渲染 SKILL.md */
async function showSkillMd(dir) {
  $("#drawer-title").textContent = "SKILL.md";
  $("#drawer-body").innerHTML = '<div class="loading">读取中…</div>';
  $("#drawer").classList.remove("hidden");
  $("#drawer-mask").classList.remove("hidden");
  try {
    const r = await api("/api/skill-detail", { path: dir });
    $("#drawer-body").innerHTML = `<div class="md-doc"><h2 class="md-title">${r.name}</h2>${renderMd(r.content)}</div>`;
  } catch (e) {
    $("#drawer-body").innerHTML = `<div class="none">读取失败：${e.message}</div>`;
  }
}

/* ---------------- matrix ---------------- */
async function loadMatrix() {
  const wrap = $("#matrix-wrap");
  wrap.innerHTML = '<div class="loading">正在扫描 skills…</div>';
  try {
    const roots = [...new Set([...(SETTINGS.roots || []), SETTINGS.download_dir].filter(Boolean))];
    MATRIX = await api("/api/matrix", { roots: roots.length ? roots : null });
    renderMatrix();
  } catch (e) {
    wrap.innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
  }
}

function renderMatrix() {
  const wrap = $("#matrix-wrap");
  if (!MATRIX || !MATRIX.rows.length) {
    wrap.innerHTML = '<div class="placeholder">扫描目录中没有找到 skill（含 SKILL.md 的目录）。可在「设置」里添加扫描目录。</div>';
    return;
  }
  // 只显示本机实际识别到的平台（与顶栏/管理页一致；一个都没检出时回退全部）
  const detectedAgents = new Set(visiblePlatforms().map((p) => p.agent));
  const cols = MATRIX.platforms.filter((p) => detectedAgents.has(p.id));
  const useCols = cols.length ? cols : MATRIX.platforms;
  const thead = useCols
    .map((p) => `<th><span class="th-plat">${logoImg(p.id, "plat-logo-sm")}${metaOf(p.id, p.name).short}</span></th>`)
    .join("");
  const rows = MATRIX.rows
    .map((row) => {
      const cells = useCols
        .map((p) => {
          const cell = row.cells.find((c) => c.agent === p.id);
          if (!cell) return "<td></td>";
          const [label, cls] = TIER_LABEL[cell.tier] || [cell.tier, ""];
          return `<td class="cell" data-skill="${row.skill}" data-agent="${p.id}"><span class="badge ${cls}">${label}</span></td>`;
        })
        .join("");
      return `<tr class="${row.valid ? "" : "invalid"}"><td class="skill-name">${row.skill}<span class="dir" title="${row.dir}">${row.dir}</span></td>${cells}</tr>`;
    })
    .join("");
  wrap.innerHTML = `<div class="matrix-scroll"><div class="matrix-card"><table class="matrix"><thead><tr><th class="skill-col">Skill</th>${thead}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
  wrap.querySelectorAll("td.cell").forEach((td) =>
    td.addEventListener("click", () => openDrawer(td.dataset.skill, td.dataset.agent))
  );
}

/* ---------------- adaptation drawer ---------------- */
function openDrawer(skill, agent) {
  const row = MATRIX.rows.find((r) => r.skill === skill);
  if (!row) return;
  const cell = row.cells.find((c) => c.agent === agent);
  if (!cell) return;
  const [label, cls] = TIER_LABEL[cell.tier] || [cell.tier, ""];
  $("#drawer-title").innerHTML = `${skill} → ${agent} <span class="badge ${cls}">${label}</span>`;

  const li = (arr, emptyMsg) =>
    arr && arr.length ? `<ul>${arr.map((x) => `<li>${x}</li>`).join("")}</ul>` : `<div class="none">${emptyMsg}</div>`;

  let adaptSection = "";
  if (cell.tier === "adapted") {
    adaptSection = `
      <h3>L2 适配（BYOK）</h3>
      <div class="none">规则层判定存在可降级缺口，LLM 适配可产出可安装变体；产物需人工确认后才落盘。</div>
      <div style="margin-top:10px"><button id="btn-run-adapt" class="btn btn-primary">运行 LLM 适配</button></div>
      <div id="adapt-result" style="margin-top:12px"></div>`;
  }

  $("#drawer-body").innerHTML = `
    <h3>判定原因</h3>${li(cell.reasons, "—")}
    <h3>能力缺口</h3>${li(cell.gaps, "无")}
    <h3>需确认项（caveat）</h3>${li(cell.caveats, "无")}
    ${cell.resident_tokens != null ? `<h3>常驻成本粗估</h3><div class="none">降级为常驻 rules 后约 ${cell.resident_tokens} tokens 每次会话（字符数/4，粗估）</div>` : ""}
    ${adaptSection}
  `;

  const btn = $("#btn-run-adapt");
  if (btn) {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "适配中…（调用 BYOK 模型）";
      $("#adapt-result").innerHTML = "";
      try {
        const r = await api("/api/adapt", { skill, agent, dir: row.dir });
        renderAdaptResult(r);
      } catch (e) {
        $("#adapt-result").innerHTML = `<div class="none">失败：${e.message}</div>`;
      } finally {
        btn.disabled = false;
        btn.textContent = "运行 LLM 适配";
      }
    });
  }
}

function changelogTable(changelog) {
  if (!changelog || !changelog.length) return "";
  const rows = changelog
    .map((c) => {
      const act = c.action || "?";
      return `<tr>
        <td>${c.block}</td>
        <td class="act-${act}">${act}</td>
        <td>${c.reason || ""}</td>
        <td>${c.lost || ""}</td>
        <td>${c.replacement || ""}</td>
      </tr>`;
    })
    .join("");
  return `<table class="changelog"><thead><tr><th>Block</th><th>动作</th><th>原因</th><th>丢失内容</th><th>替代</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderAdaptResult(r) {
  const box = $("#adapt-result");
  if (r.status === "pending" || r.status === "confirmed") {
    box.innerHTML = `
      <div class="none">状态：<span class="status-${r.status}">${r.status}</span>${r.reused ? "（复用已固化产物）" : ""} · 模型 ${r.model}</div>
      ${changelogTable(r.changelog)}
      ${r.notes ? `<div class="pc-notes">模型备注：${r.notes}</div>` : ""}
      ${r.status === "pending" ? `<div class="pc-actions"><button class="btn btn-primary" onclick="confirmAdaptation('${r.id}')">确认并安装</button><button class="btn" onclick="rejectAdaptation('${r.id}')">放弃</button></div>` : "<div class='none'>已确认安装。</div>"}
    `;
    refreshPendingDot();
  } else {
    box.innerHTML = `<div class="none">未能产出适配产物（${r.status}）：${r.message || ""}</div>`;
  }
}

async function confirmAdaptation(id) {
  try {
    const r = await api("/api/adaptations/confirm", { id });
    toast(r.ok ? `已安装到 ${r.dest}` : `确认失败：${r.message}`);
    closeDrawer();
  } catch (e) {
    toast(`确认失败：${e.message}`);
  }
}

async function rejectAdaptation(id) {
  try {
    await api("/api/adaptations/reject", { id });
    toast("已放弃该适配产物");
    closeDrawer();
  } catch (e) {
    toast(`操作失败：${e.message}`);
  }
}

/* ---------------- pending ---------------- */
async function loadPending() {
  const box = $("#pending-list");
  box.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api("/api/adaptations");
    const items = data.adaptations;
    refreshPendingDot(items.filter((a) => a.status === "pending").length);
    if (!items.length) {
      box.innerHTML = '<div class="placeholder">暂无适配产物。在适配矩阵中点击「需适配确认」格子的「运行 LLM 适配」。</div>';
      return;
    }
    box.innerHTML = items.map((a) => {
      const actions =
        a.status === "pending"
          ? `<div class="pc-actions"><button class="btn btn-primary" onclick="confirmAdaptation('${a.id}')">确认并安装</button><button class="btn" onclick="rejectAdaptation('${a.id}')">放弃</button></div>`
          : "";
      return `<div class="pending-card">
        <div class="pc-head">
          <h3>${a.skill} → ${a.agent} <span class="status-${a.status}">${a.status}</span></h3>
          <div class="meta">模型 ${a.model} · ${a.created_at} · hash ${a.source_hash.slice(0, 8)}</div>
        </div>
        ${changelogTable(a.changelog)}
        ${a.notes ? `<div class="pc-notes">模型备注：${a.notes}</div>` : ""}
        ${actions}
      </div>`;
    }).join("");
  } catch (e) {
    box.innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
  }
}

async function refreshPendingDot(explicit) {
  try {
    let n = explicit;
    if (n == null) {
      const data = await api("/api/adaptations?status=pending");
      n = data.adaptations.length;
    }
    $("#pending-dot-mg").classList.toggle("hidden", n === 0);
  } catch (e) { /* ignore */ }
}

function closeDrawer() {
  $("#drawer").classList.add("hidden");
  $("#drawer-mask").classList.add("hidden");
}
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-mask").addEventListener("click", closeDrawer);

/* ---------------- matrix apply-all ---------------- */
$("#btn-apply-all").addEventListener("click", async () => {
  if (!MATRIX || !MATRIX.rows.length) return toast("没有可应用的 skill");
  const oneClick = [];
  for (const row of MATRIX.rows) {
    if (!row.valid) continue;
    for (const cell of row.cells) {
      if (cell.tier === "full" || cell.tier === "full*") oneClick.push({ agent: cell.agent, skill: row.skill });
    }
  }
  if (!oneClick.length) return toast("没有「一键用」档位的格子可应用");
  if (!SETTINGS.roots.length) return toast("请先在设置中配置扫描目录");
  const byAgent = {};
  for (const item of oneClick) (byAgent[item.agent] = byAgent[item.agent] || []).push(item.skill);
  let ok = 0, fail = 0;
  for (const [agent, skills] of Object.entries(byAgent)) {
    for (const root of SETTINGS.roots) {
      try {
        const r = await api("/api/apply", { root, agent, skills });
        r.results.forEach((res) => (res.ok ? ok++ : fail++));
      } catch (e) {
        fail += skills.length;
      }
    }
  }
  toast(`全部应用完成：成功 ${ok}，失败 ${fail}`);
  loadMatrix();
});
$("#btn-refresh").addEventListener("click", loadMatrix);

/* ---------------- settings ---------------- */
async function loadSettings() {
  try {
    SETTINGS = await api("/api/settings");
    $("#roots-input").value = SETTINGS.roots.join("\n");
    $("#download-dir-input").value = SETTINGS.download_dir || "";
  } catch (e) {
    toast(`读取设置失败：${e.message}`);
  }
}

$("#btn-save-roots").addEventListener("click", async () => {
  const roots = $("#roots-input").value.split("\n").map((s) => s.trim()).filter(Boolean);
  try {
    SETTINGS = await api("/api/settings", { roots, download_dir: SETTINGS.download_dir || null });
    toast("已保存");
  } catch (e) {
    toast(`保存失败：${e.message}`);
  }
});

$("#btn-save-dl").addEventListener("click", async () => {
  const dir = $("#download-dir-input").value.trim();
  if (!dir) return toast("请填写下载库目录");
  try {
    SETTINGS = await api("/api/settings", { roots: SETTINGS.roots, download_dir: dir });
    toast("下载目录已保存");
  } catch (e) {
    toast(`保存失败：${e.message}`);
  }
});

/* ---------------- llm config ---------------- */
$("#btn-llm-save").addEventListener("click", async () => {
  const body = {
    base_url: $("#llm-url").value.trim(),
    api_key: $("#llm-key").value.trim(),
    model: $("#llm-model").value.trim(),
  };
  if (!body.base_url || !body.api_key || !body.model) return toast("Base URL / API Key / 模型名都需要填写");
  const btn = $("#btn-llm-save");
  btn.disabled = true; btn.textContent = "保存并探测中…";
  try {
    const r = await api("/api/llm/config", body);
    renderProbe(r);
    ping();
  } catch (e) {
    renderProbe({ ok: false, message: e.message });
  } finally {
    btn.disabled = false; btn.textContent = "保存并自动识别";
  }
});

$("#btn-llm-test").addEventListener("click", async () => {
  const btn = $("#btn-llm-test");
  btn.disabled = true;
  try {
    renderProbe(await api("/api/llm/test", {}));
  } catch (e) {
    renderProbe({ ok: false, message: e.message });
  } finally {
    btn.disabled = false;
  }
});

function renderProbe(r) {
  const el = $("#llm-probe");
  el.classList.remove("hidden", "ok", "err");
  el.classList.add(r.ok ? "ok" : "err");
  let html = `${r.ok ? "✓" : "✗"} ${r.message || ""}`;
  if (r.ok && Array.isArray(r.detected) && r.detected.length) {
    html += "<br>" + r.detected
      .slice(0, 30)
      .map((m) => `<span class="model-chip ${m === $("#llm-model").value.trim() ? "exact" : ""}">${m}</span>`)
      .join("");
    if (r.detected.length > 30) html += ` …共 ${r.detected.length} 个`;
  }
  el.innerHTML = html;
  if (r.ok) toast("模型配置已生效");
}

/* ---------------- market（搜索小卡片 + 本地导入） ---------------- */
$("#btn-search").addEventListener("click", async () => {
  const q = $("#discover-input").value.trim();
  if (!q) return toast("请输入关键词");
  const btn = $("#btn-search");
  btn.disabled = true; btn.textContent = "搜索并审计中…";
  const box = $("#discover-results");
  box.innerHTML = '<div class="loading">正在搜索并审计（GitHub + skills.sh 双源，并行审计前 5 仓，约需 10–40 秒）…</div>';
  try {
    const data = await api("/api/search", { query: q, limit: 5 });
    const msg = $("#discover-message");
    if (data.message) {
      msg.textContent = data.message;
      msg.classList.remove("hidden");
    } else {
      msg.classList.add("hidden");
    }
    renderDiscover(data.results, data.cached);
  } catch (e) {
    box.innerHTML = `<div class="loading">搜索失败：${e.message}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "搜索并审计";
  }
});

const AUDIT_BADGE = {
  pass: ["✓ 通过", "badge-pass"],
  findings: ["⚠ 有发现", "badge-findings"],
  blocked: ["✗ 已拦截", "badge-blocked"],
  skipped: ["– 未分级", "badge-skipped"],
};

/* 每个 skill 一张小卡片，一行多张；审计详情折叠成小徽章 */
function renderDiscover(results, cached) {
  const box = $("#discover-results");
  if (!results.length) {
    box.innerHTML = '<div class="placeholder">没有匹配结果。</div>';
    return;
  }
  const cards = [];
  for (const repo of results) {
    const [label, cls] = AUDIT_BADGE[repo.audit.badge] || [repo.audit.badge, ""];
    const skills = repo.audit.skills || [];
    const installTargets = skills.length ? skills : [{ name: repo.full_name.split("/").pop(), summary: repo.description || "" }];
    for (const s of installTargets) {
      cards.push(`<div class="mkt-card">
        <div class="mkt-name mkt-link" data-url="${repo.html_url}" title="在浏览器打开 ${repo.full_name}">${s.name} <span class="mkt-ext">↗</span></div>
        <div class="mkt-repo" title="${repo.full_name}">${repo.full_name} ★${repo.stars ?? 0}${repo.installs ? ` · ⬇${repo.installs.toLocaleString()}` : ""}${cached ? " · (缓存)" : ""}</div>
        <div class="mkt-sum" title="${(s.summary || repo.description || "").replace(/"/g, "&quot;")}">${(s.summary || repo.description || "—").slice(0, 90)}</div>
        <div class="mkt-foot">
          <span class="badge ${cls}">${label}</span>
          <button class="btn btn-primary mkt-install" data-source="${repo.html_url}">安装到本地库</button>
        </div>
      </div>`);
    }
  }
  box.innerHTML = `<div class="mkt-grid">${cards.join("")}</div>`;
  box.querySelectorAll(".mkt-install").forEach((b) =>
    b.addEventListener("click", () => downloadToLibrary(b.dataset.source, b))
  );
  box.querySelectorAll(".mkt-link").forEach((n) =>
    n.addEventListener("click", () => openExternal(n.dataset.url))
  );
}

async function downloadToLibrary(source, btn) {
  const old = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "下载中…"; }
  try {
    const r = await api("/api/download", { source: `${source}.git` });
    const ok = r.results.filter((x) => x.ok).length;
    const blocked = r.results.filter((x) => !x.ok);
    toast(`已下载 ${ok} 个 skill 到本地库${blocked.length ? `（${blocked.length} 个被审计拦截）` : ""}`);
    if (btn) btn.textContent = "✓ 已入库";
  } catch (e) {
    toast(`下载失败：${e.message}`);
    if (btn) btn.textContent = old;
  } finally {
    if (btn) btn.disabled = false;
  }
}

$("#btn-import").addEventListener("click", async () => {
  const p = $("#import-path").value.trim();
  if (!p) return toast("请先填写本地 skill 目录路径");
  const btn = $("#btn-import");
  btn.disabled = true; btn.textContent = "审计中…";
  const box = $("#discover-message");
  try {
    const r = await api("/api/import", { path: p });
    box.textContent = `✓ 审计${r.audit.badge === "pass" ? "通过" : "有发现（" + r.audit.detail + "）"}：已导入 ${r.skill} 到 Skill 库（${r.dir}）`;
    box.classList.remove("hidden");
    toast(`已导入：${r.skill}`);
  } catch (e) {
    box.textContent = `导入失败：${e.message}`;
    box.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.textContent = "导入到 Skill 库";
  }
});

/* ---------------- boot ---------------- */
(async function boot() {
  await ping();
  try { SETTINGS = await api("/api/settings"); } catch (e) { /* keep defaults */ }
  setView("home");
  refreshPendingDot();
})();
