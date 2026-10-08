/* Tardigrade-skill desktop frontend — CC Switch v3 style (dark, topbar, provider cards) */
"use strict";

const $ = (sel) => document.querySelector(sel);
let MATRIX = null;
let SETTINGS = { roots: [] };
let INSTALLED = null;
let SELECTED_PLATFORM = localStorage.getItem("tardigrade.platform") || "claude-code";

const TIER_LABEL = {
  "full": ["✓ 一键用", "tier-full"],
  "full*": ["✓* 可用需确认", "tier-full-star"],
  "adapted": ["⚠ 需适配确认", "tier-adapted"],
  "partial": ["¶ 手动步骤", "tier-partial"],
  "incompatible": ["✗ 不兼容", "tier-incompatible"],
};

const VIEW_TITLES = {
  home: "",
  matrix: "适配矩阵",
  skills: "Skills",
  pending: "待确认",
  discover: "发现",
  settings: "设置",
};

async function api(path, body) {
  const opts = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    let msg = `${resp.status}`;
    try { msg = (await resp.json()).detail || msg; } catch (e) { /* ignore */ }
    throw new Error(msg);
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

/* ---------------- navigation (topbar-driven, cc-switch pattern) ---------------- */
function setView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
  document.body.dataset.view = name;

  // header: back button + view title (cc-switch: 非 providers 视图显示 ← + 标题)
  const title = VIEW_TITLES[name] || name;
  $("#view-title").textContent = title;
  $("#view-title").classList.toggle("hidden", name === "home");
  $("#btn-back").classList.toggle("hidden", name === "home");
  $("#platform-pill").classList.toggle("hidden", name !== "home");
  $("#btn-go-discover").classList.toggle("hidden", name !== "home");

  document.querySelectorAll(".nav-btn").forEach((b) => {
    b.classList.toggle("current", b.dataset.view === name);
  });

  if (name === "home") loadHome();
  if (name === "matrix") loadMatrix();
  if (name === "skills") loadSkills();
  if (name === "pending") loadPending();
  if (name === "settings") loadSettings();
}

document.querySelectorAll("[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

function switchView(name) {
  setView(name);
}

/* ---------------- home (cc-switch providers view: single-column provider cards) ---------------- */
const AGENT_META = {
  "claude-code": { icon: "◈", color: "#d97757", short: "Claude" },
  "codex": { icon: "◉", color: "#10a37f", short: "Codex" },
  "gemini-cli": { icon: "✦", color: "#4285f4", short: "Gemini" },
  "cursor": { icon: "▣", color: "#9ca3af", short: "Cursor" },
  "opencode": { icon: "⌘", color: "#a78bfa", short: "OpenCode" },
};

async function loadHome() {
  const box = $("#home-list");
  box.innerHTML = '<div class="loading">加载中…</div>';
  try {
    INSTALLED = await api("/api/installed");
    renderPlatformPill();
    renderHome();
  } catch (e) {
    box.innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
  }
}

function renderPlatformPill() {
  const pill = $("#platform-pill");
  pill.innerHTML = INSTALLED.platforms
    .map((p) => {
      const meta = AGENT_META[p.agent] || { icon: "◆", color: "#9ca3af", short: p.name };
      return `<button class="as-btn ${p.agent === SELECTED_PLATFORM ? "active" : ""}" data-platform="${p.agent}" title="${p.name}">
        <span class="as-glyph" style="color:${meta.color}">${meta.icon}</span>${meta.short}
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

function renderHome() {
  const box = $("#home-list");
  const p = platformOf(SELECTED_PLATFORM);
  const meta = AGENT_META[SELECTED_PLATFORM] || { icon: "◆", color: "#9ca3af" };
  if (!p.skills.length) {
    box.innerHTML = `<div class="prov-empty">该平台还没有通过 Tardigrade 安装的 skill<br>
      <span style="color:var(--muted-fg);font-size:12px">点右上角 <span style="color:var(--orange)">＋</span> 去发现页搜索安装，或在「适配矩阵」应用已有 skill</span></div>`;
    return;
  }
  // cc-switch 语义：当前启用的供应商高亮 emerald → 对应最近安装且仍在位的 skill
  const times = p.skills.filter((s) => s.present).map((s) => s.installed_at || "");
  const latest = times.length ? Math.max(...times) : null;

  box.innerHTML = p.skills
    .map((s) => {
      const pill = s.present
        ? String(s.source || "").startsWith("http")
          ? '<span class="prov-pill pill-repo">仓库安装</span>'
          : '<span class="prov-pill pill-matrix">矩阵应用</span>'
        : '<span class="prov-pill pill-missing">缺失</span>';
      const when = s.installed_at ? s.installed_at.slice(0, 10) : "";
      const status = s.present
        ? `<span class="prov-when">⏱ ${when}</span><span class="prov-ok">✓ 在位</span>`
        : `<span class="prov-err">ⓘ 安装目录不存在</span>`;
      const state = !s.present ? "state-missing" : (latest && s.installed_at === latest ? "state-current" : "");
      return `<div class="prov-card ${state}">
        <span class="prov-grip">⠿</span>
        <div class="prov-avatar" style="color:${meta.color}">${meta.icon}</div>
        <div class="prov-main">
          <div class="prov-title-row"><span class="prov-name">${s.skill}</span>${pill}</div>
          <div class="prov-path" title="${s.dest}">${s.dest}</div>
        </div>
        <div class="prov-status">${status}
          <button class="prov-uninstall" onclick="uninstallSkill('${s.skill}', '${SELECTED_PLATFORM}')">卸载</button>
        </div>
      </div>`;
    })
    .join("");
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
        : "未配置。请在 ~/.tardigrade/models.toml 中填写 [default] 段（base_url / api_key / model）。";
      el.className = "llm-status " + (s.configured ? "ok" : "missing");
    }
  } catch (e) { /* ignore */ }
}

/* ---------------- matrix ---------------- */
async function loadMatrix() {
  const wrap = $("#matrix-wrap");
  wrap.innerHTML = '<div class="loading">正在扫描 skills…</div>';
  try {
    MATRIX = await api("/api/matrix", { roots: SETTINGS.roots.length ? SETTINGS.roots : null });
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
  const thead = MATRIX.platforms.map((p) => `<th>${p.name}</th>`).join("");
  const rows = MATRIX.rows
    .map((row) => {
      const cells = MATRIX.platforms
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
  wrap.innerHTML = `<div class="matrix-card"><table class="matrix"><thead><tr><th class="skill-col">Skill</th>${thead}</tr></thead><tbody>${rows}</tbody></table></div>`;

  wrap.querySelectorAll("td.cell").forEach((td) => {
    td.addEventListener("click", () => openDrawer(td.dataset.skill, td.dataset.agent));
  });
}

/* ---------------- drawer ---------------- */
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
        const r = await api("/api/adapt", { skill, agent });
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
    refreshPendingCount();
  } else {
    box.innerHTML = `<div class="none">未能产出适配产物（${r.status}）：${r.message || ""}</div>`;
  }
}

async function confirmAdaptation(id) {
  try {
    const r = await api("/api/adaptations/confirm", { id });
    toast(r.ok ? `已安装到 ${r.dest}` : `确认失败：${r.message}`);
    closeDrawer();
    loadPending();
  } catch (e) {
    toast(`确认失败：${e.message}`);
  }
}

async function rejectAdaptation(id) {
  try {
    await api("/api/adaptations/reject", { id });
    toast("已放弃该适配产物");
    closeDrawer();
    loadPending();
  } catch (e) {
    toast(`操作失败：${e.message}`);
  }
}

/* ---------------- pending view (HITL) ---------------- */
async function loadPending() {
  const box = $("#pending-list");
  box.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api("/api/adaptations");
    const items = data.adaptations;
    refreshPendingCount(items.filter((a) => a.status === "pending").length);
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

async function refreshPendingCount(explicit) {
  try {
    let n = explicit;
    if (n == null) {
      const data = await api("/api/adaptations?status=pending");
      n = data.adaptations.length;
    }
    const el = $("#pending-count");
    el.classList.toggle("hidden", n === 0);
  } catch (e) { /* ignore */ }
}

function closeDrawer() {
  $("#drawer").classList.add("hidden");
  $("#drawer-mask").classList.add("hidden");
}
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-mask").addEventListener("click", closeDrawer);

/* ---------------- apply ---------------- */
$("#btn-apply-all").addEventListener("click", async () => {
  if (!MATRIX || !MATRIX.rows.length) return toast("没有可应用的 skill");
  const oneClick = [];
  for (const row of MATRIX.rows) {
    if (!row.valid) continue;
    for (const cell of row.cells) {
      if (cell.tier === "full" || cell.tier === "full*") oneClick.push({ agent: cell.agent, skill: row.skill });
    }
  }
  if (!oneClick.length) return toast("没有「一键用」档位的格子可应用（需适配档请等 HITL 流程）");
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

/* ---------------- skills view ---------------- */
async function loadSkills() {
  const box = $("#skills-list");
  box.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api("/api/skills", { roots: SETTINGS.roots.length ? SETTINGS.roots : null });
    if (!data.skills.length) {
      box.innerHTML = '<div class="placeholder">没有找到 skill。可在「设置」里添加扫描目录。</div>';
      return;
    }
    box.innerHTML = data.skills
      .map((s) => {
        const reqs = s.requires
          ? Object.entries(s.requires).filter(([, v]) => v).map(([k]) => k)
          : [];
        return `<div class="skill-card">
          <h3>${s.name}${s.valid ? "" : " ⚠"}</h3>
          <p>${(s.description || s.problems[0] || "").slice(0, 140)}</p>
          <div class="chips">
            ${reqs.map((r) => `<span class="chip">${r}</span>`).join("")}
            <span class="chip">${(s.scripts || []).length} scripts</span>
            <span class="chip">${s.blocks ?? 0} blocks</span>
          </div>
        </div>`;
      })
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="loading">加载失败：${e.message}</div>`;
  }
}

/* ---------------- llm config (settings) ---------------- */
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

/* ---------------- discover (search = audit) ---------------- */
$("#btn-search").addEventListener("click", async () => {
  const q = $("#discover-input").value.trim();
  if (!q) return toast("请输入关键词");
  const btn = $("#btn-search");
  btn.disabled = true; btn.textContent = "搜索并审计中…";
  const box = $("#discover-results");
  box.innerHTML = '<div class="loading">正在搜索并逐仓审计（每仓浅拉取 + 静态安全门）…</div>';
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
  pass: ["✓ 审计通过", "badge-pass"],
  findings: ["⚠ 有发现", "badge-findings"],
  blocked: ["✗ 危险，已拦截", "badge-blocked"],
  skipped: ["– 未分级", "badge-skipped"],
};

function renderDiscover(results, cached) {
  const box = $("#discover-results");
  if (!results.length) {
    box.innerHTML = '<div class="placeholder">没有匹配结果。</div>';
    return;
  }
  box.innerHTML = results
    .map((r) => {
      const [label, cls] = AUDIT_BADGE[r.audit.badge] || [r.audit.badge, ""];
      const skills = (r.audit.skills || [])
        .map((s) => {
          const [sl, sc] = AUDIT_BADGE[s.badge] || [s.badge, ""];
          return `<div>${s.name} <span class="badge ${sc}">${sl}</span> <span style="color:var(--muted-fg)">${s.detail || ""} · ${s.summary || ""}</span></div>`;
        })
        .join("");
      return `<div class="repo-card">
        <div class="rc-head">
          <h3><a href="${r.html_url}" target="_blank" rel="noopener">${r.full_name}</a> ★${r.stars}${cached ? " <span style='color:var(--muted-fg);font-size:11px'>(缓存)</span>" : ""}</h3>
          <span class="badge ${cls}">${label} ${r.audit.detail || ""}</span>
        </div>
        <div class="rc-meta">${r.description || ""}</div>
        <div class="rc-skills">${skills || '<span style="color:var(--muted-fg)">未找到 skill</span>'}</div>
        <div class="pc-actions"><button class="btn btn-primary" onclick="installRepo('${r.html_url}')">安装到 ${"{{agent}}"}</button></div>
      </div>`;
    })
    .join("");
  box.querySelectorAll(".pc-actions .btn").forEach((b) => {
    b.textContent = `安装到 ${$("#discover-agent").value}`;
  });
}

async function installRepo(htmlUrl) {
  const agent = $("#discover-agent").value;
  const repoPath = htmlUrl.replace("https://github.com/", "");
  try {
    const r = await api("/api/install", { source: `https://github.com/${repoPath}.git`, agent });
    const ok = r.results.filter((x) => x.ok).length;
    const fail = r.results.length - ok;
    toast(`安装完成：成功 ${ok}，失败 ${fail}${fail ? "（详见审计/适配判定）" : ""}`);
    if (ok) {
      SELECTED_PLATFORM = agent;
      localStorage.setItem("tardigrade.platform", agent);
      setView("home");
    }
  } catch (e) {
    toast(`安装失败：${e.message}`);
  }
}

/* ---------------- settings (roots) ---------------- */
async function loadSettings() {
  try {
    SETTINGS = await api("/api/settings");
    $("#roots-input").value = SETTINGS.roots.join("\n");
  } catch (e) {
    toast(`读取设置失败：${e.message}`);
  }
}

$("#btn-save-roots").addEventListener("click", async () => {
  const roots = $("#roots-input").value.split("\n").map((s) => s.trim()).filter(Boolean);
  try {
    SETTINGS = await api("/api/settings", { roots });
    toast("已保存");
  } catch (e) {
    toast(`保存失败：${e.message}`);
  }
});

/* ---------------- boot ---------------- */
(async function boot() {
  await ping();
  try { SETTINGS = await api("/api/settings"); } catch (e) { /* keep defaults */ }
  setView("home");
  refreshPendingCount();
})();
