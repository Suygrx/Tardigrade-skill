/* tardigrade-skill desktop frontend — adaptation matrix */
"use strict";

const $ = (sel) => document.querySelector(sel);
let MATRIX = null;
let SETTINGS = { roots: [] };

const TIER_LABEL = {
  "full": ["✓ 一键用", "tier-full"],
  "full*": ["✓* 可用需确认", "tier-full-star"],
  "adapted": ["⚠ 需适配确认", "tier-adapted"],
  "partial": ["¶ 手动步骤", "tier-partial"],
  "incompatible": ["✗ 不兼容", "tier-incompatible"],
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

/* ---------------- navigation ---------------- */
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    $(`#view-${btn.dataset.view}`).classList.add("active");
    if (btn.dataset.view === "matrix") loadMatrix();
    if (btn.dataset.view === "skills") loadSkills();
    if (btn.dataset.view === "settings") loadSettings();
  });
});

/* ---------------- health ---------------- */
async function ping() {
  try {
    const h = await api("/api/health");
    $("#health-badge").textContent = `● 已连接 · v${h.version}`;
  } catch (e) {
    $("#health-badge").textContent = "● 未连接";
  }
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

  $("#drawer-body").innerHTML = `
    <h3>判定原因</h3>${li(cell.reasons, "—")}
    <h3>能力缺口</h3>${li(cell.gaps, "无")}
    <h3>需确认项（caveat）</h3>${li(cell.caveats, "无")}
    ${cell.resident_tokens != null ? `<h3>常驻成本粗估</h3><div class="none">降级为常驻 rules 后约 ${cell.resident_tokens} tokens 每次会话（字符数/4，粗估）</div>` : ""}
  `;
  $("#drawer").classList.remove("hidden");
  $("#drawer-mask").classList.remove("hidden");
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
  if (!oneClick.length) return toast("没有「一键用」档位的格子可应用（需适配档请等 M2 HITL 流程）");
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

/* ---------------- settings ---------------- */
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
  loadMatrix();
})();
