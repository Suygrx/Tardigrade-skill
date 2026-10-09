/* Tardigrade-skill desktop frontend — CC Switch style (dark, topbar, skills management) */
"use strict";

const $ = (sel) => document.querySelector(sel);
let MATRIX = null;
let SETTINGS = { roots: [], download_dir: "" };
let INSTALLED = null;
let LIBRARY = null;
let SELECTED_PLATFORM = localStorage.getItem("tardigrade.platform") || "claude-code";
const MANAGE = { rows: [], platforms: [], filter: null, q: "", expanded: new Set() };

const TIER_LABELS = {
  zh: {
    "full": ["已装配", "tier-full"],
    "full*": ["未装配", "tier-full-star"],
    "adapted": ["需适配", "tier-adapted"],
    "partial": ["需手动操作", "tier-partial"],
    "incompatible": ["不兼容", "tier-incompatible"],
  },
  en: {
    "full": ["Assembled", "tier-full"],
    "full*": ["Not assembled", "tier-full-star"],
    "adapted": ["Needs adaptation", "tier-adapted"],
    "partial": ["Manual action", "tier-partial"],
    "incompatible": ["Incompatible", "tier-incompatible"],
  },
};
const TIER_LABEL = () => TIER_LABELS[LANG] || TIER_LABELS.zh;

/* ---------------- i18n ---------------- */
let LANG = localStorage.getItem("tardigrade.lang") || "zh";
const I18N = {
  zh: {
    manage_btn: "Skills 管理", tab_skills: "Skills", tab_matrix: "适配性测试", tab_pending: "待确认", tab_settings: "设置",
    import_local: "导入本地 skill", import_hint: "导入会先安全审计（CRITICAL 拦截），然后落入本地 Skill 库", import_go: "审计并导入",
    ph_import: "填写含 SKILL.md 的目录绝对路径，如 D:////my-skills////pdf-tools",
    matrix_desc: "每个 skill × 本机识别到的平台给出明确结论（可左右滑动查看）",
    refresh: "刷新", apply_all: "全部应用",
    tier_full: "已装配", tier_full_star: "未装配", tier_adapted: "需适配", tier_partial: "需手动操作", tier_incompatible: "不兼容",
    pending_lead: "LLM 适配产物在确认前不会落盘安装。请核对改动清单（changelog）后决定。",
    settings_roots_h3: "Skills 扫描目录（每行一个）", settings_dl_h3: "Skill 下载库目录（市场安装 / 本地导入的落库位置）",
    settings_llm_h3: "BYOK 模型（L2 适配，任意 OpenAI 兼容端点）", settings_lang_h3: "界面语言 / Language",
    save_dl: "保存下载目录", save_roots: "保存扫描目录", llm_save: "保存并自动识别", llm_test: "重新探测",
    settings_llm_hint: "保存后自动探测端点（GET /models）并列出可用模型；探测不打消耗 token 的请求。密钥只进 LLM 请求，永不落库、不上锁文件。",
    connecting: "连接中…", cancel: "取消", confirm: "确认",
    market_desc: "搜索即审计：GitHub + skills.sh 双源检索，统一下载到本地 Skill 库，适配哪个平台由 Skills 管理里按需开启",
    ph_market: "关键词，如 pdf、github、log…", search_btn: "搜索并审计", market_placeholder: "输入关键词开始搜索。",
    ph_mg_search: "搜索已安装技能的名称、描述或仓库…",
    view_manage: "Skills 管理", view_discover: "市场",
    loading: "加载中…", uninstall: "卸载", batch_adapt: "一键适配",
    in_place: "✓ 在位", missing_dir: "ⓘ 安装目录不存在", pill_repo: "仓库安装", pill_matrix: "矩阵应用", pill_missing: "缺失", pill_local: "本机已有", pill_lib: "库",
    home_empty: "该平台还没有安装任何 skill", home_empty_hint: "点右上角 <span style=\"color:var(--orange)\">＋</span> 去「市场」搜索安装，或在「Skills 管理」导入本地 skill",
    mg_none: "没有匹配的 skill", mg_hidden_more: "另有 {n} 个匹配的 skill 被平台过滤隐藏（尚未在任何平台开启）——", mg_hidden_all: "共找到 {n} 个匹配的 skill，但都被平台过滤隐藏（尚未开启）——", mg_clear: "清除平台过滤",
    mg_on: "：使用中（点击取消使用，本地库保留）", mg_off: "：未使用（点击开启）",
    matrix_scanning: "正在扫描 skills…", matrix_none: "扫描目录中没有找到 skill（含 SKILL.md 的目录）。可在「设置」里添加扫描目录。",
    ch_block: "Block", ch_action: "动作", ch_reason: "原因", ch_lost: "丢失内容", ch_repl: "替代",
    act_kept: "保留", act_rewritten: "改写", act_dropped: "删除",
    confirm_install: "确认并安装", reject: "放弃", model_note: "模型注：", adapted_to: "适配到",
    read_md: "查看 SKILL.md", detail_title: "SKILL.md", detail_loading: "读取中…", detail_err: "读取失败：",
    dl_btn: "安装到本地库", dl_doing: "下载中…", dl_ok: "已入库",
    installed_pos: "已开启", local_only: "本机",
    uninstalled: "已卸载：", uninstall_fail: "卸载失败：", load_fail: "加载失败：", open_fail: "打开失败：",
    pill_import: "本地导入", detected_here: "检测于本机", view_md: "查看 SKILL.md",
    health_ok: "● 已连接 · ", health_bad: "● 未连接", llm_ok: "● 模型已配置 · ", llm_bad: "● BYOK 模型未配置",
    llm_cfg: "已配置：", llm_uncfg: "未配置。请在下方填写 Base URL / API Key / 模型名（或编辑 ~/.tardigrade/models.toml）。",
    chip_all: "全部", title_detected: "（检测到本机存在其非空配置目录）", title_del: "删除（本地库 + 已开启的平台）",
    delete_confirm: "删除「{s}」？将移除：{w}。该操作不可恢复。", delete_nowhere: "（未在任何位置找到，仅清记录）",
    lib: "本地库", lib_fail: "本地库：", delete_partial: "删除完成但有失败：", deleted_ok: "已删除「{s}」（{n} 处）",
    confirm_off: "确定在 {p} 上取消使用「{s}」？不会删除 skill，本地库保留，再次点击图标即可重新开启。", enable_fail: "开启失败：", enabled_to: "已开启：",
    disabled_to: "已取消使用：",
    ask_adapt: "当前 {p} 不适配「{s}」（{t}），是否要进行适配性处理？", adapting: "适配中…（调用 BYOK 模型，产物需确认后安装）",
    adapt_pending_ok: "适配产物已生成，请到「Skills 管理 → 待确认」确认安装", adapt_status: "适配结果：", adapt_fail: "适配失败：",
    no_adapt_plan: "当前 {p} 不适配「{s}」（{t}），暂无自动适配方案",
    batch_btn_title: "对该 skill 的全部检测平台批量适配（分桶执行）",
    grp_meta: "{n} 个 skill",
    batch_confirm: "对「{s}」的全部本机平台执行批量适配？\n能力齐全的平台会直接安装（不消耗 token），需要改写的平台各跑一次模型，产物进入「待确认」。",
    batch_running: "批量适配中…（并行执行，约几十秒）", batch_done: "批量适配完成：", batch_noop: "无动作", batch_fail: "批量适配失败：",
    l2_h3: "L2 适配（BYOK）", l2_desc: "规则层判定存在可降级缺口，LLM 适配可产出可安装变体；产物需人工确认后才落盘。",
    run_adapt: "运行 LLM 适配", adapt_running_btn: "适配中…（调用 BYOK 模型）", fail_prefix: "失败：",
    judge_h3: "判定原因", gaps_h3: "能力缺口", caveats_h3: "需确认项（caveat）", resident_h3: "常驻成本粗估",
    resident_desc: "降级为常驻 rules 后约 {n} tokens 每次会话（字符数/4，粗估）", li_none: "无",
    status_label: "状态：", reused_suffix: "（复用已固化产物）", model_prefix: "模型 ",
    confirmed_done: "已确认安装。", no_product: "未能产出适配产物（{s}）：{m}",
    installed_to: "已安装到 ", confirm_fail: "确认失败：", rejected: "已放弃该适配产物", op_fail: "操作失败：",
    pending_empty: "暂无适配产物。在适配矩阵中点击「需适配确认」格子的「运行 LLM 适配」。",
    nothing_to_apply: "没有可应用的 skill", no_oneclick: "没有「一键可用」档位的格子可应用", set_roots_first: "请先在设置中配置扫描目录",
    apply_done: "全部应用完成：成功 {ok}，失败 {fail}", settings_load_fail: "读取设置失败：", saved: "已保存", save_fail: "保存失败：",
    dl_dir_required: "请填写下载库目录", dl_dir_saved: "下载目录已保存",
    llm_required: "Base URL / 模型名都需要填写", llm_saving: "保存并探测中…", llm_key_saved: "已保存（留空保持不变）",
    detected_n: " …共 {n} 个", llm_effective: "模型配置已生效",
    kw_required: "请输入关键词", searching: "搜索并审计中…",
    searching_long: "正在搜索并审计（GitHub + skills.sh 双源，并行审计前 5 仓，约需 10–40 秒）…", search_fail: "搜索失败：",
    no_results: "没有匹配结果。", open_repo_title: "在浏览器打开 {s}", cached_suffix: " · (缓存)",
    dl_fail: "下载失败：", dl_intercept: "下载失败：{n} 个全部被审计拦截（{d}）", dl_see_audit: "详见审计详情",
    dl_none: "下载失败：仓库里没有找到可用 skill", dl_done: "已下载 {n} 个 skill 到本地库{x}，到「Skills 管理」开启",
    dl_blocked_suffix: "（{n} 个被审计拦截）", in_lib: "✓ 已入库（{n}）",
    path_required: "请先填写本地 skill 目录路径", auditing: "审计中…",
    import_ok: "：已导入 {s} 到 Skill 库（{d}），可在下方按平台开启", imported: "已导入：", import_fail: "导入失败：",
  },
  en: {
    manage_btn: "Skills 管理", tab_skills: "Skills", tab_matrix: "Compatibility Test", tab_pending: "Pending", tab_settings: "Settings",
    import_local: "Import local skill", import_hint: "Imports pass a security audit (CRITICAL rejected) and land in the local library", import_go: "Audit & import",
    ph_import: "Absolute path of a directory containing SKILL.md, e.g. D:////my-skills////pdf-tools",
    matrix_desc: "Every skill × every detected platform, with a clear verdict (scroll horizontally)",
    refresh: "Refresh", apply_all: "Apply all",
    tier_full: "Assembled", tier_full_star: "Not assembled", tier_adapted: "Needs adaptation", tier_partial: "Manual action", tier_incompatible: "Incompatible",
    pending_lead: "Adapted products are not installed until you confirm them. Review the changelog first.",
    settings_roots_h3: "Skill scan directories (one per line)", settings_dl_h3: "Skill library directory (where market installs / imports land)",
    settings_llm_h3: "BYOK model (L2 adaptation, any OpenAI-compatible endpoint)", settings_lang_h3: "界面语言 / Language",
    save_dl: "Save library dir", save_roots: "Save scan dirs", llm_save: "Save & detect", llm_test: "Re-detect",
    settings_llm_hint: "After saving, the endpoint is probed (GET /models) without consuming tokens. Keys only travel in LLM requests — never persisted.",
    connecting: "Connecting…", cancel: "Cancel", confirm: "OK",
    market_desc: "Search with built-in audit: GitHub + skills.sh dual-source; everything downloads into the local library — enable per platform in Skills 管理",
    ph_market: "keyword, e.g. pdf, github, log…", search_btn: "Search & audit", market_placeholder: "Type a keyword to start.",
    ph_mg_search: "Search installed skills by name, description or repo…",
    view_manage: "Skills 管理", view_discover: "Market",
    loading: "Loading…", uninstall: "Uninstall", batch_adapt: "Adapt all",
    in_place: "✓ present", missing_dir: "ⓘ install dir missing", pill_repo: "from repo", pill_matrix: "via matrix", pill_missing: "missing", pill_local: "on device", pill_lib: "library",
    home_empty: "No skills installed on this platform yet", home_empty_hint: "Use the <span style=\"color:var(--orange)\">＋</span> button (top right) to search the market, or import a local skill in Skills 管理",
    mg_none: "No matching skill", mg_hidden_more: "{n} more matching skill(s) hidden by the platform filter (not enabled anywhere) — ", mg_hidden_all: "Found {n} matching skill(s), all hidden by the platform filter (not enabled) — ", mg_clear: "clear platform filter",
    mg_on: ": in use (click to stop using — library kept)", mg_off: ": not in use (click to enable)",
    matrix_scanning: "Scanning skills…", matrix_none: "No skill (a directory with SKILL.md) found in scan dirs. Add them in Settings.",
    ch_block: "Block", ch_action: "Action", ch_reason: "Reason", ch_lost: "Lost", ch_repl: "Replacement",
    act_kept: "kept", act_rewritten: "rewritten", act_dropped: "dropped",
    confirm_install: "Confirm & install", reject: "Discard", model_note: "Model notes: ", adapted_to: "→",
    read_md: "view SKILL.md", detail_title: "SKILL.md", detail_loading: "Reading…", detail_err: "Failed to read: ",
    dl_btn: "Install to library", dl_doing: "Downloading…", dl_ok: "In library",
    installed_pos: "enabled", local_only: "device",
    uninstalled: "Uninstalled: ", uninstall_fail: "Uninstall failed: ", load_fail: "Failed to load: ", open_fail: "Failed to open: ",
    pill_import: "local import", detected_here: "detected on device", view_md: "View SKILL.md",
    health_ok: "● connected · ", health_bad: "● disconnected", llm_ok: "● model configured · ", llm_bad: "● BYOK model not configured",
    llm_cfg: "Configured: ", llm_uncfg: "Not configured. Fill Base URL / API Key / model below (or edit ~/.tardigrade/models.toml).",
    chip_all: "All", title_detected: " (a non-empty config dir was detected on this machine)", title_del: "Delete (library + enabled platforms)",
    delete_confirm: "Delete \"{s}\"? This will remove: {w}. This cannot be undone.", delete_nowhere: "(found nowhere, clearing records only)",
    lib: "library", lib_fail: "library: ", delete_partial: "Deleted with some failures: ", deleted_ok: "Deleted \"{s}\" ({n} place(s))",
    confirm_off: "Stop using \"{s}\" on {p}? The skill is NOT deleted — it stays in the library; click the icon again to re-enable.", enable_fail: "Enable failed: ", enabled_to: "Enabled: ",
    disabled_to: "Stopped using: ",
    ask_adapt: "{p} does not natively support \"{s}\" ({t}). Run adaptation?", adapting: "Adapting… (calling the BYOK model; confirm before install)",
    adapt_pending_ok: "Adapted product generated — confirm it in Skills 管理 → Pending", adapt_status: "Adapt result: ", adapt_fail: "Adapt failed: ",
    no_adapt_plan: "{p} does not support \"{s}\" ({t}); no automatic adaptation available",
    batch_btn_title: "Batch-adapt this skill across all detected platforms (bucketed)",
    grp_meta: "{n} skills",
    batch_confirm: "Batch-adapt \"{s}\" across all local platforms?\nFully compatible platforms install directly (no tokens); each platform needing a rewrite runs one model call; products go to Pending.",
    batch_running: "Batch adapting… (in parallel, tens of seconds)", batch_done: "Batch adaptation finished: ", batch_noop: "nothing to do", batch_fail: "Batch adaptation failed: ",
    l2_h3: "L2 adaptation (BYOK)", l2_desc: "Rule-level verdict found degradable gaps; LLM adaptation can produce an installable variant; the product must be confirmed before it lands on disk.",
    run_adapt: "Run LLM adaptation", adapt_running_btn: "Adapting… (calling BYOK model)", fail_prefix: "Failed: ",
    judge_h3: "Verdict reasons", gaps_h3: "Capability gaps", caveats_h3: "Caveats", resident_h3: "Resident-cost estimate",
    resident_desc: "~{n} tokens per session after downgrading to resident rules (chars/4, rough)", li_none: "none",
    status_label: "Status: ", reused_suffix: " (reused fixated product)", model_prefix: "model ",
    confirmed_done: "Confirmed & installed.", no_product: "No adapted product produced ({s}): {m}",
    installed_to: "Installed to ", confirm_fail: "Confirm failed: ", rejected: "Discarded the adapted product", op_fail: "Operation failed: ",
    pending_empty: "No adapted products yet. Click \"Run LLM adaptation\" on a \"needs adaptation\" cell in the compatibility matrix.",
    nothing_to_apply: "No skills to apply", no_oneclick: "No one-click-ready cells to apply", set_roots_first: "Configure scan directories in Settings first",
    apply_done: "Apply-all finished: {ok} succeeded, {fail} failed", settings_load_fail: "Failed to load settings: ", saved: "Saved", save_fail: "Save failed: ",
    dl_dir_required: "Enter the library directory first", dl_dir_saved: "Library directory saved",
    llm_required: "Base URL / model are required", llm_saving: "Saving & probing…", llm_key_saved: "saved (leave empty to keep)",
    detected_n: " … {n} total", llm_effective: "Model configuration applied",
    kw_required: "Enter a keyword first", searching: "Searching & auditing…",
    searching_long: "Searching & auditing (GitHub + skills.sh dual source, auditing top 5 repos in parallel, ~10–40 s)…", search_fail: "Search failed: ",
    no_results: "No results.", open_repo_title: "Open {s} in browser", cached_suffix: " · (cached)",
    dl_fail: "Download failed: ", dl_intercept: "Download failed: all {n} blocked by audit ({d})", dl_see_audit: "see audit detail",
    dl_none: "Download failed: no usable skill found in the repo", dl_done: "Downloaded {n} skill(s) to the library{x}; enable them in Skills 管理",
    dl_blocked_suffix: " ({n} blocked by audit)", in_lib: "✓ In library ({n})",
    path_required: "Enter a local skill directory path first", auditing: "Auditing…",
    import_ok: ": imported {s} to the library ({d}); enable it per platform below", imported: "Imported: ", import_fail: "Import failed: ",
  },
};
const t = (k) => (I18N[LANG] && I18N[LANG][k]) || I18N.zh[k] || k;
const tf = (k, vars) => {
  let s = t(k);
  if (vars) for (const [key, v] of Object.entries(vars)) s = s.split("{" + key + "}").join(String(v));
  return s;
};

function applyStaticLang() {
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  $("#view-title").textContent = VIEW_TITLES[document.body.dataset.view] || "";
  const sel = $("#lang-select");
  if (sel) sel.value = LANG;
}
document.addEventListener("change", async (e) => {
  if (e.target.id !== "lang-select") return;
  LANG = e.target.value;
  localStorage.setItem("tardigrade.lang", LANG);
  try { await api("/api/settings", { roots: SETTINGS.roots || [], download_dir: SETTINGS.download_dir || null, language: LANG }); } catch (err) { /* 服务端记录失败不影响 UI */ }
  applyStaticLang();
  closeDrawer(); // 抽屉内已渲染文本不会自动重译，直接关闭
  renderPlatformPill(); renderHome(); renderManage(); renderMatrix(); loadPending();
  ping(); // 刷新连接/模型徽章与设置页动态行（已连接、已配置 等）
});

const VIEW_TITLES = { home: "", get manage() { return t("view_manage"); }, get discover() { return t("view_discover"); } };

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
  try { await api("/api/open-url", { url }); } catch (e) { toast(t("open_fail") + e.message); }
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
  // 非主页隐藏第二行后顶栏变矮，内容区上移保持与顶栏贴合
  document.body.classList.toggle("pill-hidden", name !== "home");
  $("#btn-manage").classList.toggle("current", name === "manage");
  $("#btn-go-discover").classList.toggle("hidden", name === "discover");

  if (name === "home") loadHome();
  if (name === "manage") loadManage();
}

document.querySelectorAll("[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

/* 顶栏 ⚙：打开 Skills 管理里的设置面板 */
$("#btn-settings").addEventListener("click", () => {
  setView("manage");
  mgTab("settings");
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
const PNG_LOGOS = new Set(["goose", "droid", "crush", "roo", "kilo", "iflow-cli", "workbuddy"]);

function logoImg(agent, cls = "") {
  const short = metaOf(agent).short;
  const ext = PNG_LOGOS.has(agent) ? "png" : "svg";
  return `<img class="plat-logo ${cls}" src="logos/${agent}.${ext}" alt="${short}" title="${short}" onerror="this.classList.add('logo-missing')">`;
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
      return `<button class="as-btn ${p.agent === SELECTED_PLATFORM ? "active" : ""}" data-platform="${p.agent}" title="${p.name}${t("title_detected")}">
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
  box.innerHTML = '<div class="loading">' + t("loading") + '</div>';
  try {
    INSTALLED = await api("/api/installed");
    renderPlatformPill();
    renderHome();
  } catch (e) {
    box.innerHTML = `<div class="loading">${t("load_fail")}${e.message}</div>`;
  }
}

function renderHome() {
  const box = $("#home-list");
  const p = platformOf(SELECTED_PLATFORM);
  const meta = metaOf(SELECTED_PLATFORM);
  if (!p.skills.length) {
    box.innerHTML = `<div class="prov-empty">${t("home_empty")}<br>
      <span style="color:var(--muted-fg);font-size:12px">${t("home_empty_hint")}</span></div>`;
    return;
  }
  const managedTimes = p.skills.filter((s) => s.managed && s.present).map((s) => s.installed_at || "");
  const latest = managedTimes.length ? Math.max(...managedTimes) : null;

  box.innerHTML = p.skills
    .map((s) => {
      let pill;
      if (!s.present) pill = '<span class="prov-pill pill-missing">' + t("pill_missing") + '</span>';
      else if (!s.managed) pill = '<span class="prov-pill pill-matrix">' + t("pill_local") + '</span>';
      else if (String(s.source || "").startsWith("http")) pill = '<span class="prov-pill pill-repo">' + t("pill_repo") + '</span>';
      else if (s.source) pill = '<span class="prov-pill pill-repo">' + t("pill_import") + '</span>';
      else pill = '<span class="prov-pill pill-matrix">' + t("pill_matrix") + '</span>';
      const when = s.installed_at ? s.installed_at.slice(0, 10) : "";
      const status = !s.present
        ? `<span class="prov-err">${t("missing_dir")}</span>`
        : s.managed
          ? `<span class="prov-when">⏱ ${when}</span><span class="prov-ok">${t("in_place")}</span>`
          : `<span class="prov-when">${t("detected_here")}</span>`;
      const state = s.managed && s.present && latest && s.installed_at === latest ? "state-current" : (!s.present ? "state-missing" : "");
      const uninstallBtn = s.present
        ? `<button class="prov-uninstall" onclick="uninstallSkill('${s.skill}', '${SELECTED_PLATFORM}')">${t("uninstall")}</button>`
        : "";
      return `<div class="prov-card ${state}">
        <span class="prov-grip">⠿</span>
        <div class="prov-avatar">${logoImg(SELECTED_PLATFORM)}</div>
        <div class="prov-main">
          <div class="prov-title-row"><span class="prov-name prov-name-link" data-dir="${s.dest}" title="${t("view_md")}">${s.skill}</span>${pill}</div>
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
    toast(r.ok ? t("uninstalled") + r.removed : r.message);
    loadHome();
  } catch (e) {
    toast(t("uninstall_fail") + e.message);
  }
}

$("#btn-go-discover").addEventListener("click", () => switchView("discover"));

/* ---------------- health ---------------- */
async function ping() {
  try {
    const h = await api("/api/health");
    $("#health-badge").textContent = t("health_ok") + `v${h.version}`;
  } catch (e) {
    $("#health-badge").textContent = t("health_bad");
  }
  try {
    const s = await api("/api/llm-status");
    $("#llm-badge").textContent = s.configured ? t("llm_ok") + s.model : t("llm_bad");
    const el = $("#llm-status");
    if (el) {
      el.textContent = s.configured
        ? t("llm_cfg") + `${s.model} @ ${s.base_url}`
        : t("llm_uncfg");
      el.className = "llm-status " + (s.configured ? "ok" : "missing");
    }
    // 启动回填：已配置的模型把 Base URL / 模型名填回表单，key 只显示打码提示（留空 = 保持不变）
    if (s.configured) {
      const urlEl = $("#llm-url"), keyEl = $("#llm-key"), modelEl = $("#llm-model");
      if (urlEl && !urlEl.value.trim()) urlEl.value = s.base_url || "";
      if (modelEl && !modelEl.value.trim()) modelEl.value = s.model || "";
      if (keyEl) keyEl.placeholder = t("llm_key_saved") + (s.api_key_masked ? ` (${s.api_key_masked})` : "");
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
  MD_CACHE.clear(); // 库可能已变化，SKILL.md 缓存失效
  $("#mg-list").innerHTML = '<div class="loading">' + t("loading") + '</div>';
  try {
    const [lib, inst] = await Promise.all([api("/api/library"), api("/api/installed")]);
    LIBRARY = lib;
    INSTALLED = inst;
    buildManageRows();
    renderManage();
  } catch (e) {
    $("#mg-list").innerHTML = `<div class="loading">${t("load_fail")}${e.message}</div>`;
  }
}

function buildManageRows() {
  const rows = new Map();
  for (const s of LIBRARY.skills) {
    rows.set(s.name, { name: s.name, dir: s.dir, inLib: true, source: s.source || "", enabled: {} });
  }
  for (const p of INSTALLED.platforms) {
    for (const s of p.skills) {
      let row = rows.get(s.skill);
      if (!row) {
        row = { name: s.skill, dir: s.dest, inLib: false, source: "", enabled: {} };
        rows.set(s.skill, row);
      }
      if (s.present) row.enabled[p.agent] = true;
    }
  }
  MANAGE.rows = [...rows.values()].sort((a, b) => a.name.localeCompare(b.name));
  MANAGE.platforms = visiblePlatforms();
}

/* 库分组：同一个开源仓库（market:<repo-url>）下的多个 skill 归为一组统一管理 */
function groupKeyOf(r) {
  if (r.source && r.source.startsWith("market:")) return r.source.slice("market:".length);
  return "row:" + r.name;
}
function groupLabelOf(key) {
  if (key.startsWith("row:")) return key.slice(4);
  try {
    const u = new URL(key);
    const parts = u.pathname.replace(/\.git$/, "").split("/").filter(Boolean);
    return parts.slice(-2).join("/") || key;
  } catch (e) { return key; }
}

function renderManage() {
  const chips = $("#mg-chips");
  const counts = {};
  for (const p of MANAGE.platforms) counts[p.agent] = MANAGE.rows.filter((r) => r.enabled[p.agent]).length;
  chips.innerHTML =
    `<button class="mg-chip ${MANAGE.filter === null ? "active" : ""}" data-p="">${t("chip_all")} <span>${MANAGE.rows.length}</span></button>` +
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
  const matchQ = (r) => !q || r.name.toLowerCase().includes(q) || r.dir.toLowerCase().includes(q);
  // 搜索时忽略平台过滤（否则刚下载、尚未在任何平台开启的 skill 会被平台芯片隐藏）
  const rows = MANAGE.rows.filter((r) => (q ? matchQ(r) : !MANAGE.filter || r.enabled[MANAGE.filter]));
  const hiddenByFilter = q && MANAGE.filter ? MANAGE.rows.filter((r) => matchQ(r) && !r.enabled[MANAGE.filter]).length : 0;

  const rowIcons = (r) => MANAGE.platforms
    .map((p) => {
      const meta = metaOf(p.agent, p.name);
      const on = !!r.enabled[p.agent];
      return `<button class="plat-toggle ${on ? "on" : ""}" data-skill="${r.name}" data-agent="${p.agent}"
        title="${meta.short}${t(on ? "mg_on" : "mg_off")}"
        style="--pc:${meta.color}">${logoImg(p.agent)}</button>`;
    })
    .join("");
  const rowHtml = (r) => `<div class="mg-row">
      <div class="mg-row-main">
        <div class="prov-title-row"><span class="mg-name" data-dir="${r.dir}" title="${t("view_md")}">${r.name}</span></div>
        <div class="mg-path" title="${r.dir}">${r.dir}</div>
      </div>
      <div class="mg-icons">${rowIcons(r)}<button class="mg-adapt" data-skill="${r.name}" data-dir="${r.dir}" title="${t("batch_btn_title")}">⚡</button><button class="mg-del" data-skill="${r.name}" title="${t("title_del")}">✕</button></div>
    </div>`;

  // 按 source 分组：同一开源仓库（market:<url>）的多个 skill 收进一个可折叠卡片
  const groups = [];
  const byKey = new Map();
  for (const r of rows) {
    const key = groupKeyOf(r);
    if (!byKey.has(key)) {
      const g = { key, label: groupLabelOf(key), rows: [], market: !key.startsWith("row:") };
      byKey.set(key, g);
      groups.push(g);
    }
    byKey.get(key).rows.push(r);
  }
  const groupHtml = (g) => {
    if (g.rows.length === 1 && !g.market) return rowHtml(g.rows[0]); // 单个本地/外部 skill 不包壳
    const open = q ? true : MANAGE.expanded.has(g.key);
    return `<div class="mg-group ${open ? "open" : ""}" data-gkey="${g.key}">
      <div class="mg-group-head">
        <span class="mg-arrow">▶</span>
        <span class="mg-group-label">${g.label}</span>
        <span class="mg-group-meta">${tf("grp_meta", { n: g.rows.length })}</span>
      </div>
      <div class="mg-group-children"><div class="mg-children-inner">${g.rows.map(rowHtml).join("")}</div></div>
    </div>`;
  };

  $("#mg-list").innerHTML = rows.length
    ? `<div class="mg-rows">` + groups.map(groupHtml).join("") + `</div>`
      + (hiddenByFilter ? `<div class="prov-empty">${tf("mg_hidden_more", { n: hiddenByFilter })}<span class="mg-clear-filter" style="color:var(--primary);cursor:pointer">${t("mg_clear")}</span></div>` : "")
    : `<div class="prov-empty">${hiddenByFilter ? `${tf("mg_hidden_all", { n: hiddenByFilter })}<span class="mg-clear-filter" style="color:var(--primary);cursor:pointer">${t("mg_clear")}</span>` : t("mg_none")}</div>`;

  $("#mg-list").querySelectorAll(".mg-group-head").forEach((h) =>
    h.addEventListener("click", () => {
      // 纯 class 切换：子行已在 DOM 中（CSS 控制显隐），不重渲染，避免闪烁
      const card = h.closest(".mg-group");
      const key = card.dataset.gkey;
      const open = !card.classList.contains("open");
      card.classList.toggle("open", open);
      if (open) MANAGE.expanded.add(key); else MANAGE.expanded.delete(key);
    })
  );
  $("#mg-list").querySelectorAll("button.plat-toggle").forEach((b) =>
    b.addEventListener("click", () => togglePlatform(b.dataset.skill, b.dataset.agent))
  );
  $("#mg-list").querySelectorAll(".mg-name").forEach((n) =>
    n.addEventListener("click", () => showSkillMd(n.dataset.dir))
  );
  $("#mg-list").querySelectorAll(".mg-adapt").forEach((b) =>
    b.addEventListener("click", (e) => { e.stopPropagation(); batchAdapt(b.dataset.skill, b.dataset.dir); })
  );
  $("#mg-list").querySelectorAll(".mg-del").forEach((b) =>
    b.addEventListener("click", () => deleteLibrarySkill(b.dataset.skill))
  );
  $("#mg-list").querySelectorAll(".mg-clear-filter").forEach((n) =>
    n.addEventListener("click", () => { MANAGE.filter = null; renderManage(); })
  );
}

async function deleteLibrarySkill(name) {
  const row = MANAGE.rows.find((r) => r.name === name);
  const agents = row ? Object.keys(row.enabled).filter((a) => row.enabled[a]) : [];
  const where = [...(row && row.inLib ? [t("lib")] : []), ...agents.map((a) => metaOf(a).short)];
  if (!(await ask(tf("delete_confirm", { s: name, w: where.join("、") || t("delete_nowhere") })))) return;
  const fails = [];
  let done = 0;
  if (row && row.inLib) {
    try { await api("/api/library/delete", { name }); done++; } catch (e) { fails.push(t("lib_fail") + e.message); }
  }
  for (const a of agents) {
    try {
      const r = await api("/api/uninstall", { skill: name, agent: a });
      if (r && r.ok === false) fails.push(metaOf(a).short);
      else done++;
    } catch (e) { fails.push(`${metaOf(a).short}：${e.message}`); }
  }
  toast(fails.length ? t("delete_partial") + fails.join("；") : tf("deleted_ok", { s: name, n: done }));
  loadManage();
  loadHome();
}

$("#mg-search").addEventListener("input", (e) => { MANAGE.q = e.target.value; renderManage(); });

async function togglePlatform(skill, agent) {
  const row = MANAGE.rows.find((r) => r.name === skill);
  if (!row) return;
  const pname = metaOf(agent).short;
  if (row.enabled[agent]) {
    if (!(await ask(tf("confirm_off", { p: pname, s: skill })))) return;
    try {
      const r = await api("/api/uninstall", { skill, agent });
      toast(r.ok ? t("disabled_to") + skill + "（" + pname + "）" : r.message);
    } catch (e) { toast(t("uninstall_fail") + e.message); }
    loadManage();
    return;
  }
  let r;
  try {
    r = await api("/api/toggle", { dir: row.dir, agent });
  } catch (e) { return toast(t("enable_fail") + e.message); }
  if (r.ok) {
    toast(t("enabled_to") + `${skill} → ${pname}`);
    loadManage();
    return;
  }
  // 不适配：弹窗询问是否走适配处理
  const [label] = TIER_LABEL()[r.tier] || [r.tier];
  if (r.tier === "adapted") {
    const go = await ask(tf("ask_adapt", { p: pname, s: skill, t: label }));
    if (!go) return;
    toast(t("adapting"));
    try {
      const res = await api("/api/adapt", { skill, agent, dir: row.dir });
      toast(res.status === "pending" ? t("adapt_pending_ok") : t("adapt_status") + res.status);
      refreshPendingDot();
    } catch (e) { toast(t("adapt_fail") + e.message); }
  } else {
    toast(tf("no_adapt_plan", { p: pname, s: skill, t: label }));
  }
}

/* skill 详情：读取并渲染 SKILL.md */
const MD_CACHE = new Map(); // dir -> {name, content}；loadManage 时清空
async function showSkillMd(dir) {
  $("#drawer-title").textContent = "SKILL.md";
  $("#drawer").classList.remove("hidden");
  $("#drawer-mask").classList.remove("hidden");
  if (MD_CACHE.has(dir)) {
    const c = MD_CACHE.get(dir);
    $("#drawer-body").innerHTML = `<div class="md-doc"><h2 class="md-title">${c.name}</h2>${renderMd(c.content)}</div>`;
    return;
  }
  $("#drawer-body").innerHTML = '<div class="loading">' + t("detail_loading") + '</div>';
  try {
    const r = await api("/api/skill-detail", { path: dir });
    MD_CACHE.set(dir, { name: r.name, content: r.content });
    $("#drawer-body").innerHTML = `<div class="md-doc"><h2 class="md-title">${r.name}</h2>${renderMd(r.content)}</div>`;
  } catch (e) {
    $("#drawer-body").innerHTML = `<div class="none">${t("detail_err")}${e.message}</div>`;
  }
}

/* ---------------- matrix ---------------- */
async function loadMatrix() {
  const wrap = $("#matrix-wrap");
  wrap.innerHTML = '<div class="loading">' + t("matrix_scanning") + '</div>';
  try {
    const roots = [...new Set([...(SETTINGS.roots || []), SETTINGS.download_dir].filter(Boolean))];
    MATRIX = await api("/api/matrix", { roots: roots.length ? roots : null });
    renderMatrix();
  } catch (e) {
    wrap.innerHTML = `<div class="loading">${t("load_fail")}${e.message}</div>`;
  }
}

function renderMatrix() {
  const wrap = $("#matrix-wrap");
  if (!MATRIX || !MATRIX.rows.length) {
    wrap.innerHTML = '<div class="placeholder">' + t("matrix_none") + '</div>';
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
          const [label, cls] = TIER_LABEL()[cell.tier] || [cell.tier, ""];
          return `<td class="cell" data-skill="${row.skill}" data-agent="${p.id}"><span class="badge ${cls}">${label}</span></td>`;
        })
        .join("");
      return `<tr class="${row.valid ? "" : "invalid"}"><td class="skill-name">${row.skill}
        <span class="dir" title="${row.dir}">${row.dir}</span></td>${cells}</tr>`;
    })
    .join("");
  wrap.innerHTML = `<div class="matrix-scroll"><div class="matrix-card"><table class="matrix"><thead><tr><th class="skill-col">Skill</th>${thead}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
  wrap.querySelectorAll("td.cell").forEach((td) =>
    td.addEventListener("click", () => openDrawer(td.dataset.skill, td.dataset.agent))
  );
}

async function batchAdapt(skill, dir) {
  if (!(await ask(tf("batch_confirm", { s: skill })))) return;
  toast(t("batch_running"));
  try {
    const r = await api("/api/adapt-batch", dir ? { skill, dir } : { skill });
    const s = r.summary || {};
    const line = Object.entries(s).map(([k, v]) => `${k}×${v}`).join("，");
    toast(t("batch_done") + (line || t("batch_noop")));
    loadManage();
    loadMatrix();
    refreshPendingDot();
  } catch (e) { toast(t("batch_fail") + e.message); }
}

/* ---------------- adaptation drawer ---------------- */
function openDrawer(skill, agent) {
  const row = MATRIX.rows.find((r) => r.skill === skill);
  if (!row) return;
  const cell = row.cells.find((c) => c.agent === agent);
  if (!cell) return;
  const [label, cls] = TIER_LABEL()[cell.tier] || [cell.tier, ""];
  $("#drawer-title").innerHTML = `${skill} → ${agent} <span class="badge ${cls}">${label}</span>`;

  const li = (arr, emptyMsg) =>
    arr && arr.length ? `<ul>${arr.map((x) => `<li>${x}</li>`).join("")}</ul>` : `<div class="none">${emptyMsg}</div>`;

  let adaptSection = "";
  if (cell.tier === "adapted") {
    adaptSection = `
      <h3>${t("l2_h3")}</h3>
      <div class="none">${t("l2_desc")}</div>
      <div style="margin-top:10px"><button id="btn-run-adapt" class="btn btn-primary">${t("run_adapt")}</button></div>
      <div id="adapt-result" style="margin-top:12px"></div>`;
  }

  $("#drawer-body").innerHTML = `
    <h3>${t("judge_h3")}</h3>${li(cell.reasons, "—")}
    <h3>${t("gaps_h3")}</h3>${li(cell.gaps, t("li_none"))}
    <h3>${t("caveats_h3")}</h3>${li(cell.caveats, t("li_none"))}
    ${cell.resident_tokens != null ? `<h3>${t("resident_h3")}</h3><div class="none">${tf("resident_desc", { n: cell.resident_tokens })}</div>` : ""}
    ${adaptSection}
  `;

  const btn = $("#btn-run-adapt");
  if (btn) {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = t("adapt_running_btn");
      $("#adapt-result").innerHTML = "";
      try {
        const r = await api("/api/adapt", { skill, agent, dir: row.dir });
        renderAdaptResult(r);
      } catch (e) {
        $("#adapt-result").innerHTML = `<div class="none">${t("fail_prefix")}${e.message}</div>`;
      } finally {
        btn.disabled = false;
        btn.textContent = t("run_adapt");
      }
    });
  }
}

function changelogTable(changelog) {
  if (!changelog || !changelog.length) return "";
  const rows = changelog
    .map((c) => {
      const act = c.action || "?";
      const actLabel = act === "kept" ? t("act_kept") : act === "rewritten" ? t("act_rewritten") : act === "dropped" ? t("act_dropped") : act;
      return `<tr>
        <td>${c.block}</td>
        <td class="act-${act}">${actLabel}</td>
        <td>${c.reason || ""}</td>
        <td>${c.lost || ""}</td>
        <td>${c.replacement || ""}</td>
      </tr>`;
    })
    .join("");
  return `<table class="changelog"><thead><tr><th>${t("ch_block")}</th><th>${t("ch_action")}</th><th>${t("ch_reason")}</th><th>${t("ch_lost")}</th><th>${t("ch_repl")}</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderAdaptResult(r) {
  const box = $("#adapt-result");
  if (r.status === "pending" || r.status === "confirmed") {
    box.innerHTML = `
      <div class="none">${t("status_label")}<span class="status-${r.status}">${r.status}</span>${r.reused ? t("reused_suffix") : ""} · ${t("model_prefix")}${r.model}</div>
      ${changelogTable(r.changelog)}
      ${r.notes ? `<div class="pc-notes">${t("model_note")}${r.notes}</div>` : ""}
      ${r.status === "pending" ? `<div class="pc-actions"><button class="btn btn-primary" onclick="confirmAdaptation('${r.id}')">${t("confirm_install")}</button><button class="btn" onclick="rejectAdaptation('${r.id}')">${t("reject")}</button></div>` : "<div class='none'>" + t("confirmed_done") + "</div>"}
    `;
    refreshPendingDot();
  } else {
    box.innerHTML = `<div class="none">${tf("no_product", { s: r.status, m: r.message || "" })}</div>`;
  }
}

async function confirmAdaptation(id) {
  try {
    const r = await api("/api/adaptations/confirm", { id });
    toast(r.ok ? t("installed_to") + r.dest : t("confirm_fail") + r.message);
    closeDrawer();
  } catch (e) {
    toast(t("confirm_fail") + e.message);
  }
}

async function rejectAdaptation(id) {
  try {
    await api("/api/adaptations/reject", { id });
    toast(t("rejected"));
    closeDrawer();
  } catch (e) {
    toast(t("op_fail") + e.message);
  }
}

/* ---------------- pending ---------------- */
async function loadPending() {
  const box = $("#pending-list");
  box.innerHTML = '<div class="loading">' + t("loading") + '</div>';
  try {
    const data = await api("/api/adaptations");
    const items = data.adaptations;
    refreshPendingDot(items.filter((a) => a.status === "pending").length);
    if (!items.length) {
      box.innerHTML = '<div class="placeholder">' + t("pending_empty") + '</div>';
      return;
    }
    box.innerHTML = items.map((a) => {
      const actions =
        a.status === "pending"
          ? `<div class="pc-actions"><button class="btn btn-primary" onclick="confirmAdaptation('${a.id}')">${t("confirm_install")}</button><button class="btn" onclick="rejectAdaptation('${a.id}')">${t("reject")}</button></div>`
          : "";
      return `<div class="pending-card">
        <div class="pc-head">
          <h3>${a.skill} → ${a.agent} <span class="status-${a.status}">${a.status}</span></h3>
          <div class="meta">${t("model_prefix")}${a.model} · ${a.created_at} · hash ${a.source_hash.slice(0, 8)}</div>
        </div>
        ${changelogTable(a.changelog)}
        ${a.notes ? `<div class="pc-notes">${t("model_note")}${a.notes}</div>` : ""}
        ${actions}
      </div>`;
    }).join("");
  } catch (e) {
    box.innerHTML = `<div class="loading">${t("load_fail")}${e.message}</div>`;
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
  if (!MATRIX || !MATRIX.rows.length) return toast(t("nothing_to_apply"));
  const oneClick = [];
  for (const row of MATRIX.rows) {
    if (!row.valid) continue;
    for (const cell of row.cells) {
      if (cell.tier === "full" || cell.tier === "full*") oneClick.push({ agent: cell.agent, skill: row.skill });
    }
  }
  if (!oneClick.length) return toast(t("no_oneclick"));
  if (!SETTINGS.roots.length) return toast(t("set_roots_first"));
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
  toast(tf("apply_done", { ok: ok, fail: fail }));
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
    toast(t("settings_load_fail") + e.message);
  }
}

$("#btn-save-roots").addEventListener("click", async () => {
  const roots = $("#roots-input").value.split("\n").map((s) => s.trim()).filter(Boolean);
  try {
    SETTINGS = await api("/api/settings", { roots, download_dir: SETTINGS.download_dir || null });
    toast(t("saved"));
  } catch (e) {
    toast(t("save_fail") + e.message);
  }
});

$("#btn-save-dl").addEventListener("click", async () => {
  const dir = $("#download-dir-input").value.trim();
  if (!dir) return toast(t("dl_dir_required"));
  try {
    SETTINGS = await api("/api/settings", { roots: SETTINGS.roots, download_dir: dir });
    toast(t("dl_dir_saved"));
  } catch (e) {
    toast(t("save_fail") + e.message);
  }
});

/* ---------------- llm config ---------------- */
$("#btn-llm-save").addEventListener("click", async () => {
  const body = {
    base_url: $("#llm-url").value.trim(),
    api_key: $("#llm-key").value.trim(),
    model: $("#llm-model").value.trim(),
  };
  if (!body.base_url || !body.model) return toast(t("llm_required"));
  const btn = $("#btn-llm-save");
  btn.disabled = true; btn.textContent = t("llm_saving");
  try {
    const r = await api("/api/llm/config", body);
    renderProbe(r);
    ping();
  } catch (e) {
    renderProbe({ ok: false, message: e.message });
  } finally {
    btn.disabled = false; btn.textContent = t("llm_save");
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
    if (r.detected.length > 30) html += tf("detected_n", { n: r.detected.length });
  }
  el.innerHTML = html;
  if (r.ok) toast(t("llm_effective"));
}

/* ---------------- market（搜索小卡片 + 本地导入） ---------------- */
$("#btn-search").addEventListener("click", async () => {
  const q = $("#discover-input").value.trim();
  if (!q) return toast(t("kw_required"));
  const btn = $("#btn-search");
  btn.disabled = true; btn.textContent = t("searching");
  const box = $("#discover-results");
  box.innerHTML = '<div class="loading">' + t("searching_long") + '</div>';
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
    box.innerHTML = `<div class="loading">${t("search_fail")}${e.message}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = t("search_btn");
  }
});

const AUDIT_BADGES = {
  zh: {
    pass: ["通过", "badge-pass"], findings: ["有发现", "badge-findings"], blocked: ["已拦截", "badge-blocked"], skipped: ["跳过", "badge-skipped"],
  },
  en: {
    pass: ["Pass", "badge-pass"], findings: ["Findings", "badge-findings"], blocked: ["Blocked", "badge-blocked"], skipped: ["Skipped", "badge-skipped"],
  },
};
const AUDIT_BADGE = () => AUDIT_BADGES[LANG] || AUDIT_BADGES.zh;

/* 每个 skill 一张小卡片，一行多张；审计详情折叠成小徽章 */
function renderDiscover(results, cached) {
  const box = $("#discover-results");
  if (!results.length) {
    box.innerHTML = '<div class="placeholder">' + t("no_results") + '</div>';
    return;
  }
  const cards = [];
  for (const repo of results) {
    const [label, cls] = AUDIT_BADGE()[repo.audit.badge] || [repo.audit.badge, ""];
    const skills = repo.audit.skills || [];
    const installTargets = skills.length ? skills : [{ name: repo.full_name.split("/").pop(), summary: repo.description || "" }];
    for (const s of installTargets) {
      cards.push(`<div class="mkt-card">
        <div class="mkt-name mkt-link" data-url="${repo.html_url}" title="${tf("open_repo_title", { s: repo.full_name })}">${s.name} <span class="mkt-ext">↗</span></div>
        <div class="mkt-repo" title="${repo.full_name}">${repo.full_name} ★${repo.stars ?? 0}${repo.installs ? ` · ⬇${repo.installs.toLocaleString()}` : ""}${cached ? t("cached_suffix") : ""}</div>
        <div class="mkt-sum" title="${(s.summary || repo.description || "").replace(/"/g, "&quot;")}">${(s.summary || repo.description || "—").slice(0, 90)}</div>
        <div class="mkt-foot">
          <span class="badge ${cls}">${label}</span>
          <button class="btn btn-primary mkt-install" data-source="${repo.html_url}">${t("dl_btn")}</button>
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
  if (btn) { btn.disabled = true; btn.textContent = t("dl_doing"); }
  try {
    const r = await api("/api/download", { source: `${source}.git` });
    const ok = r.results.filter((x) => x.ok).length;
    const blocked = r.results.filter((x) => !x.ok);
    if (!ok) {
      toast(blocked.length ? tf("dl_intercept", { n: blocked.length, d: (blocked[0].audit && blocked[0].audit.detail) || t("dl_see_audit") }) : t("dl_none"));
      return;
    }
    toast(tf("dl_done", { n: ok, x: blocked.length ? tf("dl_blocked_suffix", { n: blocked.length }) : "" }));
    if (btn) btn.textContent = tf("in_lib", { n: ok });
  } catch (e) {
    toast(t("dl_fail") + e.message);
    if (btn) btn.textContent = old;
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* Skills 管理：导入本地 skill（折叠输入行） */
$("#btn-mg-import").addEventListener("click", () => {
  $("#mg-import-row").classList.toggle("hidden");
  if (!$("#mg-import-row").classList.contains("hidden")) $("#mg-import-path").focus();
});

$("#btn-mg-import-go").addEventListener("click", async () => {
  const p = $("#mg-import-path").value.trim();
  if (!p) return toast(t("path_required"));
  const btn = $("#btn-mg-import-go");
  btn.disabled = true; btn.textContent = t("auditing");
  const box = $("#mg-import-message");
  try {
    const r = await api("/api/import", { path: p });
    box.textContent = "✓ " + (r.audit.badge === "pass" ? AUDIT_BADGE().pass[0] : AUDIT_BADGE().findings[0] + "（" + r.audit.detail + "）") + tf("import_ok", { s: r.skill, d: r.dir });
    box.classList.remove("hidden");
    toast(t("imported") + r.skill);
    $("#mg-import-path").value = "";
    loadManage();
  } catch (e) {
    box.textContent = t("import_fail") + e.message;
    box.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.textContent = t("import_go");
  }
});

/* ---------------- boot ---------------- */
(async function boot() {
  await ping();
  try { SETTINGS = await api("/api/settings"); } catch (e) { /* keep defaults */ }
  applyStaticLang();
  setView("home");
  refreshPendingDot();
})();
