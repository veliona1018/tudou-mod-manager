const state = {
  mods: [], category: "all", modelFilter: "all", filter: "all", search: "", sort: "name", selectedIds: new Set(),
};

const labels = {
  map: "地图",
  spray: "喷漆",
  survivor_model: "幸存者模型",
  infected_model: "感染者模型",
  weapon_model: "武器模型",
  prop_model: "环境模型",
  sound: "音效",
  voice_replacement: "语音替换",
  texture: "材质",
  ui: "界面",
  script: "脚本/功能",
};

const statusLabels = {
  matched: "已配对",
  missing_preview: "缺少预览图",
  image_without_vpk: "缺少 VPK",
};

const viewTitles = {
  all: "我的 Mod",
  map: "地图 Mod",
  model: "模型 Mod",
  survivor_target: "生还者角色调整",
  voice_replacement: "语音替换 Mod",
  spray: "喷漆 Mod",
};

const rootPath = document.querySelector("#root-path");
const grid = document.querySelector("#mod-grid");
const notice = document.querySelector("#notice");
const operationOverlay = document.querySelector("#operation-overlay");
const operationMessage = document.querySelector("#operation-message");
const selectionActions = document.querySelector("#selection-actions");
const selectionCount = document.querySelector("#selection-count");
const aiDialog = document.querySelector("#ai-dialog");
const aiDialogTitle = document.querySelector("#ai-dialog-title");
const aiDialogBody = document.querySelector("#ai-dialog-body");
const aiDialogClose = document.querySelector("#ai-dialog-close");
const aiHistoryList = document.querySelector("#ai-history-list");
const aiPromptSelect = document.querySelector("#ai-prompt-select");
const aiPromptInput = document.querySelector("#ai-prompt-input");
const aiRunButton = document.querySelector("#ai-run-button");
const aiSavePromptButton = document.querySelector("#ai-save-prompt-button");
const aiDeletePromptButton = document.querySelector("#ai-delete-prompt-button");
const aiAnalysisStatus = document.querySelector("#ai-analysis-status");
const aiSettingsPanel = document.querySelector("#ai-settings-panel");
const aiModelSelect = document.querySelector("#ai-model-select");
const deepseekKeyInput = document.querySelector("#deepseek-key-input");
const aiSettingsStatus = document.querySelector("#ai-settings-status");
const importPreviewDialog = document.querySelector("#import-preview-dialog");
const importPreviewList = document.querySelector("#import-preview-list");
const importPreviewSummary = document.querySelector("#import-preview-summary");
const importPreviewStatus = document.querySelector("#import-preview-status");
const importPreviewClose = document.querySelector("#import-preview-close");
const vpkFilesDialog = document.querySelector("#vpk-files-dialog");
const vpkFilesTitle = document.querySelector("#vpk-files-title");
const vpkFilesSummary = document.querySelector("#vpk-files-summary");
const vpkFilesNote = document.querySelector("#vpk-files-note");
const vpkFilesList = document.querySelector("#vpk-files-list");
const vpkFilesClose = document.querySelector("#vpk-files-close");
const nekoVpkDialog = document.querySelector("#nekovpk-dialog");
const nekoVpkTitle = document.querySelector("#nekovpk-title");
const nekoVpkSummary = document.querySelector("#nekovpk-summary");
const nekoVpkTargetList = document.querySelector("#nekovpk-target-list");
const nekoVpkClose = document.querySelector("#nekovpk-close");
const nekoVpkLoading = document.querySelector("#nekovpk-loading");
const voiceDialog = document.querySelector("#voice-dialog");
const voiceTitle = document.querySelector("#voice-title");
const voiceSummary = document.querySelector("#voice-summary");
const voiceBody = document.querySelector("#voice-body");
const voiceClose = document.querySelector("#voice-close");
const voiceInstall = document.querySelector("#voice-install");
const voiceRestore = document.querySelector("#voice-restore");
const voiceLoading = document.querySelector("#voice-loading");
const voiceLoadingMessage = document.querySelector("#voice-loading-message");
let activeImportMods = [];
let sourceVersion = null;
let reloadRequested = false;
let activeAiMod = null;
let aiPrompts = { default: null, custom: [] };
let aiHistory = [];
let operationBusy = false;

function runExclusiveOperation(message, task) {
  if (operationBusy) return Promise.resolve(false);
  operationBusy = true;
  operationMessage.textContent = message;
  operationOverlay.classList.remove("hidden");
  document.body.setAttribute("aria-busy", "true");
  return Promise.resolve()
    .then(task)
    .finally(() => {
      operationBusy = false;
      operationOverlay.classList.add("hidden");
      document.body.removeAttribute("aria-busy");
    });
}

async function checkForSourceChanges() {
  try {
    const response = await fetch("/api/source-version", { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    if (sourceVersion === null) {
      sourceVersion = payload.version;
    } else if (payload.version !== sourceVersion && !reloadRequested) {
      reloadRequested = true;
      window.location.reload();
    }
  } catch {
    // The backend may be restarting after a Python source change.
  }
}

function fileUrl(filePath) {
  return "/files/" + filePath.split("/").map(encodeURIComponent).join("/");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));
}

function effectivePrimaryCategories(mod) {
  const categoryByLabel = new Map(Object.entries(labels).map(([category, label]) => [label, category]));
  const markedCategories = (mod.customTags || [])
    .filter((tag) => tag.marked === true)
    .map((tag) => categoryByLabel.get(String(tag.label).trim()) || String(tag.label).trim())
    .filter((category) => Object.prototype.hasOwnProperty.call(labels, category));
  return [...new Set([...(mod.primaryCategories || []), ...markedCategories])];
}

function visibleMods() {
  const query = state.search.trim().toLowerCase();
  const filtered = state.mods.filter((mod) => {
    const targetNames = [
      ...(mod.characterTargets || []).map((target) => target.name),
      ...(mod.weaponTargets || []).map((target) => target.name),
    ];
    const haystack = [
      mod.name,
      ...(mod.vpkFiles || []),
      ...(mod.categories || []),
      ...targetNames,
      ...Object.values(mod.tagOverrides || {}),
    ].join(" ").toLowerCase();
    const filterMatch = state.filter === "all"
      || (state.filter === "disabled" ? mod.enabled === false : mod.status === state.filter);
    const primaryCategories = effectivePrimaryCategories(mod);
    const hasSurvivorTarget = (mod.characterTargets || []).some((target) => target.side === "survivor");
    const categoryMatch = state.category === "all"
      || primaryCategories.includes(state.category)
      || (state.category === "model" && primaryCategories.some((category) => category.endsWith("_model")))
      || (state.category === "survivor_target" && hasSurvivorTarget);
    const modelMatch = state.category !== "model"
      || state.modelFilter === "all"
      || primaryCategories.includes(state.modelFilter);
    return filterMatch && categoryMatch && modelMatch && (!query || haystack.includes(query));
  });
  return filtered.sort((left, right) => {
    if (state.sort === "vpk") return right.vpkFiles.length - left.vpkFiles.length;
    if (state.sort === "status") return left.status.localeCompare(right.status);
    return left.name.localeCompare(right.name, "zh-CN");
  });
}

function renderStats() {
  const mods = visibleMods();
  const isFiltered = state.category !== "all"
    || state.filter !== "all"
    || (state.category === "model" && state.modelFilter !== "all")
    || state.search.trim() !== "";
  document.querySelector("#total-label").textContent = isFiltered ? "当前视图" : "全部 Mod";
  document.querySelector("#total-count").textContent = mods.length;
  document.querySelector("#matched-count").textContent = mods.filter((mod) => mod.status === "matched").length;
  document.querySelector("#issue-count").textContent = mods.filter((mod) => mod.status !== "matched" || mod.errors.length).length;
}

function renderViewTitle() {
  const title = viewTitles[state.category] || viewTitles.all;
  document.querySelector("#page-title").textContent = title;
  document.querySelector("#page-eyebrow").textContent = state.category === "survivor_target"
    ? "SURVIVOR MODEL TOOLS / 02"
    : state.category === "voice_replacement"
      ? "VOICE REPLACEMENT / 03"
    : "SURVIVAL LIBRARY / 01";
}

function renderSelectionActions() {
  const availableIds = new Set(state.mods.map((mod) => mod.id));
  state.selectedIds = new Set([...state.selectedIds].filter((id) => availableIds.has(id)));
  selectionCount.textContent = state.selectedIds.size;
  selectionActions.classList.toggle("hidden", state.selectedIds.size === 0);
}

function getTagItems(mod) {
  const primaryCategories = mod.primaryCategories || [];
  const tagOverrides = mod.tagOverrides || {};
  const hiddenTags = mod.hiddenTags || {};
  const items = [];
  const addTag = (key, label, primary = false) => {
    if (Object.prototype.hasOwnProperty.call(hiddenTags, key)) return;
    items.push({ key, label: tagOverrides[key] || label, primary, custom: key.startsWith("custom:") });
  };

  (mod.characterTargets || []).forEach((target) => {
    const side = target.side === "survivor" ? "幸存者" : "感染者";
    const targetCategory = target.side === "survivor" ? "survivor_model" : "infected_model";
    addTag(
      `character:${target.side}:${target.id}`,
      `${side} · ${target.name}`,
      primaryCategories.includes(targetCategory),
    );
  });
  (mod.weaponTargets || []).forEach((target) => {
    addTag(
      `weapon:${target.id}`,
      `武器 · ${target.name}`,
      primaryCategories.includes("weapon_model"),
    );
  });
  (mod.categories || []).forEach((category) => {
    addTag(
      `category:${category}`,
      labels[category] || category,
      primaryCategories.includes(category),
    );
  });
  (mod.customTags || []).forEach((tag) => addTag(`custom:${tag.id}`, tag.label, tag.marked === true));
  return items;
}

function setCustomTagMarked(mod, key, marked) {
  const id = key.replace(/^custom:/, "");
  mod.customTags = (mod.customTags || []).map((tag) => (
    tag.id === id ? { ...tag, marked } : tag
  ));
}

function renderCard(mod) {
  const isVoiceReplacement = (mod.primaryCategories || []).includes("voice_replacement");
  const voiceInstalled = mod.voiceInstalled === true;
  const disabled = mod.enabled === false && mod.vpkFiles.length > 0;
  const selected = state.selectedIds.has(mod.id);
  const status = isVoiceReplacement
    ? (voiceInstalled ? "已替换" : "未替换")
    : (disabled ? "已停用" : (statusLabels[mod.status] || "检测错误"));
  const issue = mod.status !== "matched" || mod.errors.length > 0 || (isVoiceReplacement && !voiceInstalled);
  const hiddenTags = mod.hiddenTags || {};
  const tagItems = getTagItems(mod);
  const tags = tagItems.map((item) => `<span class="tag ${item.primary ? "primary" : ""}">${escapeHtml(item.label)}</span>`).join("") || `<span class="tag">未分类</span>`;
  const tagMenuItems = tagItems.map((item) => `
    <div class="tag-menu-row">
      <button class="tag-menu-item" data-action="edit-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(item.key)}" type="button"><i data-lucide="pencil"></i><span>${escapeHtml(item.label)}</span></button>
      ${item.custom ? `<button class="tag-menu-mark" data-action="mark-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(item.key)}" data-tag-marked="${item.primary}" type="button" title="${item.primary ? "取消主标签" : "标记为主标签"}" aria-label="${item.primary ? "取消" : "标记"} ${escapeHtml(item.label)}"><i data-lucide="${item.primary ? "badge-check" : "badge"}"></i></button>` : ""}
      <button class="tag-menu-delete" data-action="delete-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(item.key)}" data-tag-label="${escapeHtml(item.label)}" type="button" title="删除标签" aria-label="删除 ${escapeHtml(item.label)}"><i data-lucide="x"></i></button>
    </div>`).join("");
  const hiddenTagItems = Object.entries(hiddenTags).map(([key, label]) => `
    <button class="tag-menu-restore" data-action="restore-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(key)}" type="button"><i data-lucide="rotate-ccw"></i><span>恢复 ${escapeHtml(label)}</span></button>`).join("");
  const tagMenu = `<div class="tag-menu hidden" role="menu">
    <button class="tag-menu-item ai-menu-item" data-action="ai-analyze" data-mod-id="${escapeHtml(mod.id)}" type="button"><i data-lucide="sparkles"></i><span>AI 分析</span></button>
    <button class="tag-menu-item add-tag-item" data-action="add-tag" data-mod-id="${escapeHtml(mod.id)}" type="button"><i data-lucide="plus"></i><span>添加标签</span></button>
    <div class="tag-menu-divider"></div>
    ${tagMenuItems}
    ${hiddenTagItems ? `<div class="tag-menu-divider"></div>${hiddenTagItems}` : ""}
  </div>`;
  const preview = mod.preview
    ? `<img src="${fileUrl(mod.preview)}" alt="${escapeHtml(mod.name)} 预览图" loading="lazy" />`
    : `<div class="preview missing"><i data-lucide="image-off"></i></div>`;
  const error = mod.errors.length ? `<div class="error-line">${escapeHtml(mod.errors[0].error)}</div>` : "";
  const nekoVpkTargets = mod.nekovpk?.targets || [];
  const hasNekoVpkTargets = nekoVpkTargets.length > 1;
  const voiceActionLabel = voiceInstalled ? "恢复语音" : "安装语音";
  return `<article class="mod-card ${selected ? "selected" : ""}">
    <div class="preview ${mod.preview ? "" : "missing"}">
      ${preview}
    <span class="status-chip ${isVoiceReplacement ? (voiceInstalled ? "voice-installed" : "voice-uninstalled") : (disabled ? "disabled" : (issue ? "issue" : ""))}">${escapeHtml(status)}</span>
    </div>
    <div class="card-body">
      <div class="card-title"><label class="card-select" title="选择 ${escapeHtml(mod.name)}"><input class="card-select-input" type="checkbox" data-mod-id="${escapeHtml(mod.id)}" ${selected ? "checked" : ""} /><span class="sr-only">选择 ${escapeHtml(mod.name)}</span></label><h2 title="${escapeHtml(mod.name)}">${escapeHtml(mod.name)}</h2><button class="more-button" data-action="toggle-tag-menu" data-mod-id="${escapeHtml(mod.id)}" type="button" title="编辑标签" aria-label="编辑 ${escapeHtml(mod.name)} 的标签"><i data-lucide="more-horizontal"></i></button>${tagMenu}</div>
      <div class="tags">${tags}</div>
      <button class="vpk-line" data-action="show-vpk-files" data-mod-id="${escapeHtml(mod.id)}" type="button" title="查看关联的 VPK 文件" aria-label="查看 ${escapeHtml(mod.name)} 的关联 VPK 文件"><i data-lucide="package"></i><strong>${mod.vpkFiles.length}</strong> 个 VPK 文件<i class="vpk-line-arrow" data-lucide="chevron-right"></i></button>
      ${error}
      <div class="card-actions">
        ${mod.vpkFiles.length && !isVoiceReplacement ? `<button class="card-action toggle-enabled" data-action="toggle-enabled" data-mod-id="${escapeHtml(mod.id)}" type="button" title="${disabled ? "启用 VPK 文件" : "停用 VPK 文件"}"><i data-lucide="${disabled ? "play" : "pause"}"></i>${disabled ? "启用" : "停用"}</button>` : ""}
        ${hasNekoVpkTargets ? `<button class="card-action" data-action="show-nekovpk" data-mod-id="${escapeHtml(mod.id)}" type="button" title="切换 NekoVPK 生还者角色"><i data-lucide="arrow-right-left"></i>角色调整</button>` : ""}
        ${isVoiceReplacement ? `<button class="card-action" data-action="show-voice" data-mod-id="${escapeHtml(mod.id)}" type="button" title="${voiceInstalled ? "恢复原始语音" : "安装语音替换"}"><i data-lucide="${voiceInstalled ? "undo-2" : "mic-2"}"></i>${voiceActionLabel}</button>` : ""}
        <button class="card-action" data-action="rename" data-mod-id="${escapeHtml(mod.id)}" type="button"><i data-lucide="pencil"></i>重命名</button>
        <button class="card-action danger" data-action="delete" data-mod-id="${escapeHtml(mod.id)}" type="button" title="删除 Mod" aria-label="删除 ${escapeHtml(mod.name)}"><i data-lucide="trash-2"></i></button>
      </div>
    </div>
  </article>`;
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function renderVpkFiles(mod, details = []) {
  const files = mod.vpkFiles || [];
  const detailsByPath = new Map(details.map((item) => [item.path, item]));
  vpkFilesTitle.textContent = `${mod.name} · VPK 文件`;
  vpkFilesSummary.textContent = `共 ${files.length} 个文件，路径相对于当前 Mod 目录`;
  vpkFilesList.innerHTML = files.length
    ? files.map((relativePath) => {
        const enabled = /\.vpk$/i.test(relativePath);
        const fileName = relativePath.split("/").pop();
        const info = detailsByPath.get(relativePath) || {};
        const duplicate = info.duplicate === true;
        const size = info.size == null ? "" : `<span>${formatFileSize(info.size)}</span>`;
        return `<div class="vpk-file-row">
          <div class="vpk-file-icon"><i data-lucide="file-archive"></i></div>
          <div class="vpk-file-info">
            <strong title="${escapeHtml(fileName)}">${escapeHtml(fileName)}</strong>
            <span title="${escapeHtml(relativePath)}">${escapeHtml(relativePath)}</span>
            <div class="vpk-file-meta">${size}${duplicate ? `<em>内容重复</em>` : ""}</div>
          </div>
          <span class="vpk-file-status ${enabled ? "enabled" : "disabled"}">${enabled ? "已启用" : "已停用"}</span>
          <button class="vpk-file-delete" data-action="delete-vpk-file" data-mod-id="${escapeHtml(mod.id)}" data-vpk-path="${escapeHtml(relativePath)}" type="button" title="将 ${escapeHtml(fileName)} 移入回收站" aria-label="将 ${escapeHtml(fileName)} 移入回收站"><i data-lucide="trash-2"></i></button>
        </div>`;
      }).join("")
    : `<div class="vpk-files-empty">这个 Mod 没有关联的 VPK 文件</div>`;
  if (window.lucide) lucide.createIcons();
}

async function loadVpkFileDetails(mod) {
  const response = await fetch(`/api/mod/file-details?id=${encodeURIComponent(mod.id)}`, { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  if (vpkFilesDialog.open && vpkFilesDialog.dataset.modId === mod.id) {
    renderVpkFiles(mod, result.files || []);
    vpkFilesSummary.textContent = `共 ${result.files.length} 个文件，已检查内容是否重复`;
  }
}

function openVpkFiles(mod) {
  vpkFilesDialog.dataset.modId = mod.id;
  vpkFilesNote.classList.remove("hidden");
  renderVpkFiles(mod);
  if (typeof vpkFilesDialog.showModal === "function") vpkFilesDialog.showModal();
  else vpkFilesDialog.setAttribute("open", "");
  loadVpkFileDetails(mod).catch((error) => {
    vpkFilesSummary.textContent = `共 ${mod.vpkFiles.length} 个文件，重复检测失败：${error.message}`;
  });
}

function renderNekoVpkTargets(mod, info) {
  const targets = info.targets || [];
  nekoVpkTitle.textContent = `${mod.name} · 角色调整`;
  nekoVpkSummary.textContent = info.currentName
    ? `当前替换：${info.currentName}，可用预置角色 ${targets.length} 个`
    : `已发现 ${targets.length} 个可用预置角色`;
  nekoVpkTargetList.innerHTML = targets.length
    ? targets.map((target) => {
      const current = target.id === info.currentTarget;
      const sourceLabel = target.source === "neko7z"
        ? `预置资源 · ${target.fileCount} 个文件`
        : target.source === "备份"
          ? `原始备份资源 · ${target.fileCount} 个文件`
          : `当前 VPK 资源 · ${target.fileCount} 个文件`;
      return `<button class="nekovpk-target ${current ? "current" : ""}" data-action="convert-nekovpk" data-mod-id="${escapeHtml(mod.id)}" data-target-id="${escapeHtml(target.id)}" type="button" ${current ? "disabled" : ""}>
        <span class="nekovpk-target-icon"><i data-lucide="${current ? "check-circle-2" : "arrow-right-left"}"></i></span>
        <span class="nekovpk-target-info"><strong>${escapeHtml(target.name)}</strong><span>${escapeHtml(sourceLabel)}</span></span>
        <span class="nekovpk-target-state">${current ? "当前" : "切换"}</span>
      </button>`;
    }).join("")
    : `<div class="vpk-files-empty">没有发现可用的角色资源</div>`;
  if (window.lucide) lucide.createIcons();
}

async function openNekoVpk(mod) {
  nekoVpkDialog.dataset.modId = mod.id;
  nekoVpkTitle.textContent = `${mod.name} · 角色调整`;
  nekoVpkSummary.textContent = "正在读取 NekoVPK 预置角色…";
  nekoVpkTargetList.innerHTML = `<div class="vpk-files-empty">正在读取…</div>`;
  if (typeof nekoVpkDialog.showModal === "function") nekoVpkDialog.showModal();
  else nekoVpkDialog.setAttribute("open", "");
  try {
    const response = await fetch(`/api/mod/nekovpk?id=${encodeURIComponent(mod.id)}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    renderNekoVpkTargets(mod, result);
  } catch (error) {
    nekoVpkSummary.textContent = `读取失败：${error.message}`;
    nekoVpkTargetList.innerHTML = `<div class="vpk-files-empty">无法读取角色资源</div>`;
  }
}

function renderVoiceInfo(mod, info) {
  voiceDialog.dataset.modId = mod.id;
  voiceTitle.textContent = `${mod.name} · 语音替换`;
  voiceSummary.textContent = info.installed
    ? `已安装 · ${info.sourceFileCount} 个语音文件 · 可恢复原始语音`
    : `检测到 ${info.roles.length} 个角色、${info.sourceFileCount} 个语音文件`;
  const roleRows = (info.roles || []).map((role) => {
    const directories = (role.targetDirectories || []).map((directory) =>
      `<span class="voice-directory">${escapeHtml(directory.root)} · 覆盖 ${directory.overwrite} / 新增 ${directory.new}</span>`
    ).join("");
    const missing = (role.missingDirectories || []).map((directory) =>
      `<span class="voice-directory missing">缺少 ${escapeHtml(directory)}</span>`
    ).join("");
    return `<div class="voice-role-row">
      <div class="voice-role-name"><strong>${escapeHtml(role.name)}</strong><span>${role.sourceFileCount} 个 WAV</span></div>
      <div class="voice-role-targets">${directories || "<span class=\"voice-directory missing\">没有可安装的游戏目录</span>"}${missing}</div>
      <div class="voice-role-count"><span>${role.overwriteCount} 覆盖</span><span>${role.newCount} 新增</span></div>
    </div>`;
  }).join("");
  const missingRoots = (info.roles || []).flatMap((role) => role.missingDirectories || []);
  const conflictText = (info.conflicts || []).length
    ? `<div class="voice-warning">已有语音包生效：${escapeHtml(info.conflicts.map((item) => item.modName || item.modId).join("、"))}。安装时可选择替换。</div>`
    : "";
  voiceBody.innerHTML = `${conflictText}
    <div class="voice-summary-grid">
      <div><span>覆盖文件</span><strong>${info.roles.reduce((sum, role) => sum + role.overwriteCount, 0)}</strong></div>
      <div><span>新增文件</span><strong>${info.roles.reduce((sum, role) => sum + role.newCount, 0)}</strong></div>
      <div><span>安装目录</span><strong>${info.roles.reduce((sum, role) => sum + role.targetDirectories.length, 0)}</strong></div>
      <div><span>缺失目录</span><strong>${missingRoots.length}</strong></div>
    </div>
    <div class="voice-role-list">${roleRows || `<div class="vpk-files-empty">没有发现可识别的生还者语音角色</div>`}</div>`;
  voiceInstall.disabled = Boolean(info.installed) || !info.roles.some((role) => role.installable);
  voiceRestore.disabled = !info.installed;
  if (window.lucide) lucide.createIcons();
}

async function openVoiceReplacement(mod) {
  voiceDialog.dataset.modId = mod.id;
  voiceTitle.textContent = `${mod.name} · 语音替换`;
  voiceSummary.textContent = "正在读取语音包…";
  voiceBody.innerHTML = `<div class="vpk-files-empty">正在读取语音角色和目标目录…</div>`;
  voiceInstall.disabled = true;
  voiceRestore.disabled = true;
  if (typeof voiceDialog.showModal === "function") voiceDialog.showModal();
  else voiceDialog.setAttribute("open", "");
  try {
    const response = await fetch(`/api/mod/voice?id=${encodeURIComponent(mod.id)}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    renderVoiceInfo(mod, result);
  } catch (error) {
    voiceSummary.textContent = `读取失败：${error.message}`;
    voiceBody.innerHTML = `<div class="vpk-files-empty">无法读取语音包</div>`;
  }
}

function setVoiceLoading(loading, message = "正在处理语音包，请稍候…") {
  voiceLoadingMessage.textContent = message;
  voiceLoading.classList.toggle("hidden", !loading);
  voiceClose.disabled = loading;
  voiceInstall.disabled = loading;
  voiceRestore.disabled = loading;
}

async function installVoiceReplacement(mod) {
  const install = async (replaceExisting) => postJson("/api/mod/voice/install", {
    id: mod.id,
    replaceExisting,
  });
  try {
    return await install(false);
  } catch (error) {
    if (error.status !== 409) throw error;
    const conflicts = error.payload?.conflicts || [];
    const names = conflicts.map((item) => item.modName || item.modId).join("、");
    if (!window.confirm(`当前已有语音包生效：${names || "其他语音包"}。\n替换它们并安装“${mod.name}”吗？\n原语音仍会保留在备份中。`)) return null;
    return install(true);
  }
}

async function handleVoiceAction(action) {
  if (operationBusy) return;
  const mod = state.mods.find((item) => item.id === voiceDialog.dataset.modId);
  if (!mod) return;
  const isRestore = action === "restore";
  return runExclusiveOperation(isRestore ? "正在恢复原始语音，请稍候…" : "正在安装语音包，请稍候…", async () => {
    setVoiceLoading(true, isRestore ? "正在恢复原始语音，请稍候…" : "正在安装语音包并备份原文件，请稍候…");
    try {
      const result = isRestore
        ? await postJson("/api/mod/voice/restore", { id: mod.id })
        : await installVoiceReplacement(mod);
      if (!result) return;
      await loadCatalog(true);
      voiceDialog.close();
      showNotice(
        isRestore
          ? "已恢复原始语音"
          : "语音包已安装。请进入游戏执行 snd_rebuildaudiocache，完成后重启游戏。",
        true,
      );
    } catch (error) {
      showNotice(`${isRestore ? "恢复" : "安装"}语音包失败：${error.message}`);
    } finally {
      setVoiceLoading(false);
    }
  });
}

async function handleNekoVpkTargetAction(event) {
  if (operationBusy) return;
  const button = event.target.closest("button[data-action='convert-nekovpk']");
  if (!button || button.disabled) return;
  const mod = state.mods.find((item) => item.id === button.dataset.modId);
  if (!mod) return;
  const targetName = button.querySelector("strong")?.textContent || "目标角色";
  return runExclusiveOperation(`正在切换到 ${targetName}，请稍候…`, async () => {
    button.disabled = true;
    nekoVpkLoading.classList.remove("hidden");
    nekoVpkClose.disabled = true;
    nekoVpkTargetList.querySelectorAll("button").forEach((item) => { item.disabled = true; });
    try {
      const result = await postJson("/api/mod/nekovpk/convert", {
        id: mod.id,
        target: button.dataset.targetId,
      });
      await loadCatalog(true);
      nekoVpkDialog.close();
      showNotice(result.result?.changed === false ? `当前已经是“${targetName}”` : `已切换到“${targetName}”`, true);
    } catch (error) {
      showNotice(`角色切换失败：${error.message}`);
      nekoVpkTargetList.querySelectorAll("button").forEach((item) => {
        item.disabled = item.classList.contains("current");
      });
    } finally {
      nekoVpkLoading.classList.add("hidden");
      nekoVpkClose.disabled = false;
    }
  });
}

async function handleVpkFileAction(event) {
  if (operationBusy) return;
  const target = event.target;
  return runExclusiveOperation("正在处理 VPK 文件，请稍候…", () => handleVpkFileActionInner(target));
}

async function handleVpkFileActionInner(target) {
  const button = target.closest("button[data-action='delete-vpk-file']");
  if (!button || button.disabled) return;
  const mod = state.mods.find((item) => item.id === button.dataset.modId);
  const relativePath = button.dataset.vpkPath;
  if (!mod || !relativePath) return;
  const fileName = relativePath.split("/").pop();
  const isDuplicate = button.closest(".vpk-file-row")?.querySelector(".vpk-file-meta em");
  const warning = isDuplicate
    ? `\n检测到它与同组其他 VPK 内容完全相同。`
    : `\n注意：它可能是 Mod 的分卷或组成部分，移除后 Mod 可能不完整。`;
  if (!window.confirm(`确定将“${fileName}”移入回收站吗？${warning}\n之后可以从系统回收站恢复。`)) return;
  button.disabled = true;
  try {
    await postJson("/api/mod/file-delete", { id: mod.id, path: relativePath });
    await loadCatalog(true);
    const updatedMod = state.mods.find((item) => item.id === mod.id) || { ...mod, vpkFiles: mod.vpkFiles.filter((path) => path !== relativePath) };
    if (vpkFilesDialog.open) renderVpkFiles(updatedMod);
    showNotice(`已将“${fileName}”移入回收站`, true);
    loadVpkFileDetails(updatedMod).catch(() => {});
  } catch (error) {
    showNotice(`移入回收站失败：${error.message}`);
    button.disabled = false;
  }
}

function importPreviewItem(mod) {
  const tags = getTagItems(mod);
  const visibleTags = tags.length
    ? tags.map((item) => `
        <div class="import-tag-row">
          <button class="import-tag-edit ${item.primary ? "primary" : ""}" data-import-action="edit-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(item.key)}" data-tag-label="${escapeHtml(item.label)}" type="button" title="修改标签"><i data-lucide="pencil"></i><span>${escapeHtml(item.label)}</span></button>
          ${item.custom ? `<button class="import-tag-mark ${item.primary ? "active" : ""}" data-import-action="mark-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(item.key)}" data-tag-marked="${item.primary}" type="button" title="${item.primary ? "取消主标签" : "标记为主标签"}" aria-label="${item.primary ? "取消" : "标记"} ${escapeHtml(item.label)}"><i data-lucide="${item.primary ? "badge-check" : "badge"}"></i></button>` : ""}
          <button class="import-tag-delete" data-import-action="delete-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(item.key)}" data-tag-label="${escapeHtml(item.label)}" type="button" title="删除标签" aria-label="删除 ${escapeHtml(item.label)}"><i data-lucide="x"></i></button>
        </div>`).join("")
    : `<span class="import-no-tags">未检测到标签</span>`;
  const hiddenTags = Object.entries(mod.hiddenTags || {}).map(([key, label]) => `
    <button class="import-tag-restore" data-import-action="restore-tag" data-mod-id="${escapeHtml(mod.id)}" data-tag-key="${escapeHtml(key)}" type="button"><i data-lucide="rotate-ccw"></i>恢复 ${escapeHtml(label)}</button>`).join("");
  const preview = mod.preview
    ? `<img src="${fileUrl(mod.preview)}" alt="${escapeHtml(mod.name)} 预览图" loading="lazy" />`
    : `<div class="import-preview-missing"><i data-lucide="image-off"></i></div>`;
  const categoryText = (mod.primaryCategories || []).map((category) => labels[category] || category).join("、") || "未确定主类型";
  return `<article class="import-preview-item" data-mod-id="${escapeHtml(mod.id)}">
    <div class="import-preview-image">${preview}</div>
    <div class="import-preview-content">
      <div class="import-preview-title"><h3 title="${escapeHtml(mod.name)}">${escapeHtml(mod.name)}</h3><span>${mod.vpkFiles.length} 个 VPK</span></div>
      <div class="import-detection">自动检测：${escapeHtml(categoryText)}</div>
      <div class="import-preview-tags">${visibleTags}</div>
      ${hiddenTags ? `<div class="import-hidden-tags">${hiddenTags}</div>` : ""}
      <button class="import-add-tag" data-import-action="add-tag" data-mod-id="${escapeHtml(mod.id)}" type="button"><i data-lucide="plus"></i>添加标签</button>
    </div>
  </article>`;
}

function renderImportPreview() {
  importPreviewList.innerHTML = activeImportMods.map(importPreviewItem).join("");
  if (window.lucide) lucide.createIcons();
}

function setImportPreviewStatus(message, error = false) {
  importPreviewStatus.textContent = message;
  importPreviewStatus.classList.toggle("error", error);
}

function openImportPreview(mods) {
  activeImportMods = mods;
  importPreviewSummary.textContent = `本次导入检测到 ${mods.length} 个 Mod，可在完成前调整标签。`;
  setImportPreviewStatus("标签修改会立即保存到本机配置。", false);
  renderImportPreview();
  const closed = new Promise((resolve) => {
    importPreviewDialog.addEventListener("close", resolve, { once: true });
  });
  if (typeof importPreviewDialog.showModal === "function") importPreviewDialog.showModal();
  else importPreviewDialog.setAttribute("open", "");
  return closed;
}

async function handleImportPreviewAction(event) {
  if (operationBusy) return;
  const target = event.target;
  return runExclusiveOperation("正在保存标签，请稍候…", () => handleImportPreviewActionInner(target));
}

async function handleImportPreviewActionInner(target) {
  const button = target.closest("button[data-import-action]");
  if (!button || button.disabled) return;
  const mod = activeImportMods.find((item) => item.id === button.dataset.modId);
  if (!mod) return;
  const action = button.dataset.importAction;
  button.disabled = true;
  try {
    if (action === "add-tag") {
      const label = window.prompt("输入新标签名称");
      if (label === null || label.trim() === "") return;
      setImportPreviewStatus("正在保存新标签…", false);
      const result = await postJson("/api/mod/tag/add", { id: mod.id, label: label.trim() });
      mod.customTags = [...(mod.customTags || []), { id: result.key.replace(/^custom:/, ""), label: result.label }];
      setImportPreviewStatus("标签已添加", false);
    } else if (action === "mark-tag") {
      const marked = button.dataset.tagMarked !== "true";
      setImportPreviewStatus(marked ? "正在标记主标签…" : "正在取消主标签…", false);
      await postJson("/api/mod/tag/mark", { id: mod.id, key: button.dataset.tagKey, marked });
      setCustomTagMarked(mod, button.dataset.tagKey, marked);
      setImportPreviewStatus(marked ? "已标记为主标签" : "已取消主标签", false);
    } else if (action === "edit-tag") {
      const label = window.prompt("修改标签（留空可恢复自动标签）", button.dataset.tagLabel || "");
      if (label === null) return;
      setImportPreviewStatus("正在保存标签修改…", false);
      await postJson("/api/mod/tag", { id: mod.id, key: button.dataset.tagKey, label });
      mod.tagOverrides = { ...(mod.tagOverrides || {}) };
      if (label.trim()) mod.tagOverrides[button.dataset.tagKey] = label.trim();
      else delete mod.tagOverrides[button.dataset.tagKey];
      setImportPreviewStatus(label.trim() ? "标签已修改" : "标签已恢复自动名称", false);
    } else if (action === "delete-tag") {
      const label = button.dataset.tagLabel || "这个标签";
      if (!window.confirm(`确定删除“${label}”吗？`)) return;
      setImportPreviewStatus("正在删除标签…", false);
      await postJson("/api/mod/tag/delete", { id: mod.id, key: button.dataset.tagKey, label });
      if (button.dataset.tagKey.startsWith("custom:")) {
        mod.customTags = (mod.customTags || []).filter((tag) => `custom:${tag.id}` !== button.dataset.tagKey);
      } else {
        mod.hiddenTags = { ...(mod.hiddenTags || {}), [button.dataset.tagKey]: label };
      }
      setImportPreviewStatus("标签已删除", false);
    } else if (action === "restore-tag") {
      setImportPreviewStatus("正在恢复标签…", false);
      await postJson("/api/mod/tag/restore", { id: mod.id, key: button.dataset.tagKey });
      mod.hiddenTags = { ...(mod.hiddenTags || {}) };
      delete mod.hiddenTags[button.dataset.tagKey];
      setImportPreviewStatus("标签已恢复", false);
    }
    renderImportPreview();
  } catch (error) {
    setImportPreviewStatus(`标签操作失败：${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

function render() {
  const mods = visibleMods();
  renderStats();
  renderViewTitle();
  document.querySelector("#model-filters").classList.toggle("hidden", state.category !== "model");
  grid.innerHTML = mods.length ? mods.map(renderCard).join("") : `<div class="empty">没有符合条件的 Mod</div>`;
  if (window.lucide) lucide.createIcons();
  document.querySelectorAll(".card-action, .vpk-line, .more-button, .tag-menu-item, .tag-menu-mark, .tag-menu-delete, .tag-menu-restore").forEach((button) => button.addEventListener("click", handleCardAction));
  document.querySelectorAll(".card-select-input").forEach((input) => input.addEventListener("change", handleSelectionChange));
  renderSelectionActions();
}

function handleSelectionChange(event) {
  if (operationBusy) return;
  const id = event.currentTarget.dataset.modId;
  if (event.currentTarget.checked) state.selectedIds.add(id);
  else state.selectedIds.delete(id);
  render();
}

function showNotice(message, success = false) {
  notice.innerHTML = `<span class="notice-message">${escapeHtml(message)}</span><button class="notice-close" type="button" title="关闭提示" aria-label="关闭提示"><i data-lucide="x"></i></button>`;
  notice.classList.toggle("success", success);
  notice.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
}

notice.addEventListener("click", (event) => {
  if (event.target.closest(".notice-close")) notice.classList.add("hidden");
});

async function postJson(route, payload) {
  const response = await fetch(route, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.payload = result;
    throw error;
  }
  return result;
}

async function runBulkAction(action) {
  if (operationBusy) return;
  const ids = [...state.selectedIds];
  if (!ids.length) return;
  if (action === "delete" && !window.confirm(`确定将选中的 ${ids.length} 个 Mod 移入回收站吗？\n之后可从系统回收站恢复。`)) return;
  const actionLabel = action === "delete" ? "移入回收站" : action === "enable" ? "启用" : "停用";
  return runExclusiveOperation(`正在批量${actionLabel}，请稍候…`, async () => {
    const result = await postJson("/api/mod/bulk", {
      action,
      ids,
      ...(action === "enable" || action === "disable" ? { enabled: action === "enable" } : {}),
    });
    const processed = result.processed || [];
    const skipped = result.skipped || [];
    state.selectedIds.clear();
    await loadCatalog(true);
    const skippedText = skipped.length ? `，跳过 ${skipped.length} 个没有 VPK 的项目` : "";
    showNotice(`已${actionLabel} ${processed.length} 个 Mod${skippedText}`, true);
  });
}

async function getAiConfig() {
  const response = await fetch("/api/ai/config", { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

async function openAiSettings() {
  aiSettingsPanel.classList.remove("hidden");
  aiSettingsStatus.textContent = "正在读取配置…";
  try {
    const config = await getAiConfig();
    aiModelSelect.value = config.model || "deepseek-chat";
    deepseekKeyInput.value = "";
    aiSettingsStatus.textContent = config.configured ? "API Key 已配置" : "尚未配置 API Key";
  } catch (error) {
    aiSettingsStatus.textContent = `读取失败：${error.message}`;
  }
}

function closeAiSettings() {
  aiSettingsPanel.classList.add("hidden");
}

async function saveAiSettings() {
  try {
    const apiKey = deepseekKeyInput.value.trim();
    await postJson("/api/ai/config", {
      model: aiModelSelect.value,
      ...(apiKey ? { apiKey } : {}),
    });
    deepseekKeyInput.value = "";
    aiSettingsStatus.textContent = "配置已保存";
  } catch (error) {
    aiSettingsStatus.textContent = `保存失败：${error.message}`;
  }
}

async function clearAiKey() {
  try {
    await postJson("/api/ai/config", { model: aiModelSelect.value, apiKey: "" });
    deepseekKeyInput.value = "";
    aiSettingsStatus.textContent = "API Key 已清除";
  } catch (error) {
    aiSettingsStatus.textContent = `清除失败：${error.message}`;
  }
}

async function getAiPrompts() {
  const response = await fetch("/api/ai/prompts", { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

async function getAiHistory(modId) {
  const response = await fetch(`/api/mod/ai-history?id=${encodeURIComponent(modId)}`, { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result.history || [];
}

function selectedPrompt() {
  const id = aiPromptSelect.value;
  if (id === "default") return aiPrompts.default;
  return (aiPrompts.custom || []).find((prompt) => prompt.id === id) || null;
}

function renderPromptOptions(selectedId = "default") {
  const options = [aiPrompts.default, ...(aiPrompts.custom || [])].filter(Boolean);
  aiPromptSelect.innerHTML = options.map((prompt) => (
    `<option value="${escapeHtml(prompt.id)}">${escapeHtml(prompt.name)}</option>`
  )).join("");
  aiPromptSelect.value = options.some((prompt) => prompt.id === selectedId) ? selectedId : "default";
  const prompt = selectedPrompt();
  aiPromptInput.value = prompt ? prompt.prompt : "";
  aiDeletePromptButton.disabled = aiPromptSelect.value === "default";
}

function renderAiHistory() {
  if (!aiHistory.length) {
    aiHistoryList.innerHTML = `<div class="ai-history-empty">暂无分析记录</div>`;
    return;
  }
  aiHistoryList.innerHTML = aiHistory.map((entry, index) => (
    `<button class="ai-history-item ${index === 0 ? "active" : ""}" data-history-id="${escapeHtml(entry.id)}" type="button">
      <strong>${escapeHtml(entry.promptName || "AI 分析")}</strong>
      <span>${escapeHtml(entry.createdAt || "")}</span>
    </button>`
  )).join("");
  document.querySelectorAll(".ai-history-item").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll(".ai-history-item").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    const entry = aiHistory.find((item) => item.id === button.dataset.historyId);
    if (entry) showAiHistoryEntry(entry);
  }));
  showAiHistoryEntry(aiHistory[0]);
}

function showAiHistoryEntry(entry) {
  aiDialogBody.textContent = entry ? entry.analysis : "";
  aiAnalysisStatus.textContent = entry
    ? `${entry.createdAt || ""} · ${entry.model || "DeepSeek"} · ${entry.promptName || "AI 分析"}`
    : "还没有分析结果";
}

async function openAiWorkspace(mod) {
  activeAiMod = mod;
  aiDialogTitle.textContent = mod.name;
  aiDialogBody.textContent = "正在读取提示词和历史记录…";
  aiAnalysisStatus.textContent = "";
  if (!aiDialog.open) {
    if (typeof aiDialog.showModal === "function") aiDialog.showModal();
    else aiDialog.setAttribute("open", "");
  }
  try {
    const [promptData, history, config] = await Promise.all([
      getAiPrompts(),
      getAiHistory(mod.id),
      getAiConfig(),
    ]);
    aiPrompts = promptData;
    aiHistory = history;
    renderPromptOptions();
    renderAiHistory();
    if (!aiHistory.length) showAiHistoryEntry(null);
    aiAnalysisStatus.textContent = config.configured
      ? `模型：${config.model}`
      : "尚未配置 API Key，请先在左侧 AI 设置中配置";
  } catch (error) {
    aiAnalysisStatus.textContent = `读取失败：${error.message}`;
  }
}

async function configureDeepSeek() {
  const apiKey = window.prompt("请输入 DeepSeek API Key（只保存在本机）");
  if (apiKey === null || apiKey.trim() === "") return false;
  await postJson("/api/ai/config", { apiKey: apiKey.trim() });
  return true;
}

async function runAiAnalysis() {
  if (!activeAiMod) return;
  try {
    let config = await getAiConfig();
    if (!config.configured && !(await configureDeepSeek())) return;
    config = await getAiConfig();
    const prompt = aiPromptInput.value.trim();
    if (!prompt) throw new Error("分析提示词不能为空");
    const promptInfo = selectedPrompt();
    aiRunButton.disabled = true;
    aiAnalysisStatus.textContent = "正在请求 DeepSeek 分析，请稍候…";
    const result = await postJson("/api/mod/ai-analyze", {
      id: activeAiMod.id,
      promptId: aiPromptSelect.value,
      promptName: promptInfo ? promptInfo.name : "临时提示词",
      prompt,
    });
    aiHistory = [result.entry, ...aiHistory];
    renderAiHistory();
    aiAnalysisStatus.textContent = `${result.entry.createdAt} · ${config.model}`;
  } catch (error) {
    aiAnalysisStatus.textContent = `AI 分析失败：${error.message}`;
  } finally {
    aiRunButton.disabled = false;
  }
}

async function saveCurrentPrompt() {
  const selected = selectedPrompt();
  const defaultName = selected && selected.id !== "default" ? selected.name : "我的 Mod 分析";
  const name = window.prompt("自定义提示词名称", defaultName);
  if (name === null || name.trim() === "") return;
  try {
    const result = await postJson("/api/ai/prompts/save", {
      id: selected && selected.id !== "default" ? selected.id : "",
      name: name.trim(),
      prompt: aiPromptInput.value.trim(),
    });
    aiPrompts.custom = result.custom || [];
    renderPromptOptions(result.prompt.id);
    aiAnalysisStatus.textContent = "提示词已保存";
  } catch (error) {
    aiAnalysisStatus.textContent = `保存提示词失败：${error.message}`;
  }
}

async function deleteCurrentPrompt() {
  const prompt = selectedPrompt();
  if (!prompt || prompt.id === "default") return;
  if (!window.confirm(`确定删除“${prompt.name}”吗？`)) return;
  try {
    const result = await postJson("/api/ai/prompts/delete", { id: prompt.id });
    aiPrompts.custom = result.custom || [];
    renderPromptOptions("default");
    aiAnalysisStatus.textContent = "提示词已删除";
  } catch (error) {
    aiAnalysisStatus.textContent = `删除提示词失败：${error.message}`;
  }
}

async function handleCardAction(event) {
  if (operationBusy) return;
  const button = event.currentTarget;
  const action = button?.dataset.action;
  if (action === "show-vpk-files" || action === "show-nekovpk" || action === "show-voice" || action === "toggle-tag-menu") {
    return handleCardActionInner(button);
  }
  return runExclusiveOperation("正在处理 Mod 操作，请稍候…", () => handleCardActionInner(button));
}

async function handleCardActionInner(button) {
  const mod = state.mods.find((item) => item.id === button.dataset.modId);
  if (!mod) return;
  try {
    if (button.dataset.action === "show-vpk-files") {
      openVpkFiles(mod);
      return;
    }
    if (button.dataset.action === "show-nekovpk") {
      await openNekoVpk(mod);
      return;
    }
    if (button.dataset.action === "show-voice") {
      await openVoiceReplacement(mod);
      return;
    }
    if (button.dataset.action === "ai-analyze") {
      button.closest(".tag-menu").classList.add("hidden");
      button.closest(".mod-card").classList.remove("menu-open");
      await openAiWorkspace(mod);
      return;
    }
    if (button.dataset.action === "toggle-tag-menu") {
      const card = button.closest(".mod-card");
      const menu = button.closest(".card-title").querySelector(".tag-menu");
      const willOpen = menu.classList.contains("hidden");
      document.querySelectorAll(".tag-menu").forEach((item) => item.classList.add("hidden"));
      document.querySelectorAll(".mod-card.menu-open").forEach((item) => item.classList.remove("menu-open"));
      menu.classList.toggle("hidden", !willOpen);
      card.classList.toggle("menu-open", willOpen);
      return;
    }
    if (button.dataset.action === "add-tag") {
      const label = window.prompt("输入新标签名称");
      if (label === null || label.trim() === "") return;
      const result = await postJson("/api/mod/tag/add", { id: mod.id, label: label.trim() });
      mod.customTags = [...(mod.customTags || []), { id: result.key.replace(/^custom:/, ""), label: result.label }];
      render();
      showNotice("标签已添加", true);
    } else if (button.dataset.action === "mark-tag") {
      const marked = button.dataset.tagMarked !== "true";
      await postJson("/api/mod/tag/mark", {
        id: mod.id,
        key: button.dataset.tagKey,
        marked,
      });
      setCustomTagMarked(mod, button.dataset.tagKey, marked);
      render();
      showNotice(marked ? "已标记为主标签" : "已取消主标签", true);
    } else if (button.dataset.action === "delete-tag") {
      const label = button.dataset.tagLabel || "这个标签";
      if (!window.confirm(`确定删除“${label}”吗？`)) return;
      await postJson("/api/mod/tag/delete", {
        id: mod.id,
        key: button.dataset.tagKey,
        label,
      });
      if (button.dataset.tagKey.startsWith("custom:")) {
        mod.customTags = (mod.customTags || []).filter((tag) => `custom:${tag.id}` !== button.dataset.tagKey);
      } else {
        mod.hiddenTags = { ...(mod.hiddenTags || {}), [button.dataset.tagKey]: label };
      }
      render();
      showNotice("标签已删除", true);
    } else if (button.dataset.action === "restore-tag") {
      await postJson("/api/mod/tag/restore", { id: mod.id, key: button.dataset.tagKey });
      mod.hiddenTags = { ...(mod.hiddenTags || {}) };
      delete mod.hiddenTags[button.dataset.tagKey];
      render();
      showNotice("标签已恢复", true);
    } else if (button.dataset.action === "toggle-enabled") {
      const enabled = mod.enabled === false;
      await postJson("/api/mod/toggle", { id: mod.id, enabled });
      await loadCatalog(true);
      showNotice(enabled ? `已启用“${mod.name}”` : `已停用“${mod.name}”`, true);
    } else if (button.dataset.action === "rename") {
      const name = window.prompt("修改 Mod 名称", mod.name);
      if (name === null || name.trim() === "" || (name.trim() === mod.name && name.trim() === mod.originalName)) return;
      const result = await postJson("/api/mod/rename", { id: mod.id, name: name.trim() });
      const renamedVpks = result.renamed.filter((path) => /\.vpk1?$/i.test(path));
      const renamedPreviews = result.renamed.filter((path) => !/\.vpk1?$/i.test(path));
      mod.id = result.id || mod.id;
      mod.name = result.name;
      mod.originalName = result.name;
      mod.vpkFiles = renamedVpks;
      mod.previewFiles = renamedPreviews;
      mod.preview = renamedPreviews[0] || null;
      renderStats();
      render();
      showNotice(`已将 Mod 重命名为“${name.trim()}”`, true);
    } else if (button.dataset.action === "edit-tag") {
      const currentLabel = button.textContent.trim();
      const label = window.prompt("修改标签（留空可恢复自动标签）", currentLabel);
      if (label === null) return;
      await postJson("/api/mod/tag", {
        id: mod.id,
        key: button.dataset.tagKey,
        label,
      });
      mod.tagOverrides = { ...(mod.tagOverrides || {}) };
      if (label.trim()) mod.tagOverrides[button.dataset.tagKey] = label.trim();
      else delete mod.tagOverrides[button.dataset.tagKey];
      render();
      showNotice(label.trim() ? "标签已修改" : "标签已恢复自动名称", true);
    } else if (button.dataset.action === "delete") {
      const files = mod.vpkFiles.length ? `${mod.vpkFiles.length} 个 VPK` : "预览图";
      if (!window.confirm(`确定将“${mod.name}”移入回收站吗？\n将移入关联的 ${files}，之后可从系统回收站恢复。`)) return;
      await postJson("/api/mod/delete", { id: mod.id });
      state.mods = state.mods.filter((item) => item !== mod);
      renderStats();
      render();
      showNotice(`已将“${mod.name}”移入回收站`, true);
    }
  } catch (error) {
    showNotice(`操作失败：${error.message}`);
  }
}

async function loadCatalog(force = false) {
  notice.classList.add("hidden");
  try {
    const route = force ? `/api/catalog?refresh=${Date.now()}` : "/api/catalog";
    const response = await fetch(route, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.mods = payload.mods || [];
    rootPath.textContent = payload.root || "当前工作目录";
    renderStats();
    render();
    return state.mods;
  } catch (error) {
    showNotice(`目录读取失败：${error.message}`);
    grid.innerHTML = "";
  }
}

async function changeFolder() {
  if (operationBusy) return;
  return runExclusiveOperation("正在更改 Mod 目录，请稍候…", () => changeFolderInner());
}

async function changeFolderInner() {
  try {
    showNotice("请选择新的 Mod 文件夹…");
    const response = await fetch("/api/select-folder", { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    if (result.cancelled) {
      notice.classList.add("hidden");
      return;
    }
    await loadCatalog();
    showNotice(`已切换到：${result.root}`, true);
  } catch (error) {
    showNotice(`更改目录失败：${error.message}`);
  }
}

async function resetFolder() {
  if (operationBusy) return;
  return runExclusiveOperation("正在恢复默认目录，请稍候…", () => resetFolderInner());
}

async function resetFolderInner() {
  try {
    showNotice("正在恢复默认目录…");
    const response = await fetch("/api/reset-folder", { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    await loadCatalog();
    showNotice(`已恢复默认目录：${result.root}`, true);
  } catch (error) {
    showNotice(`恢复默认目录失败：${error.message}`);
  }
}

async function importArchive(file) {
  if (operationBusy) return;
  try {
    const importData = await runExclusiveOperation(`正在导入“${file.name}”，请稍候…`, async () => {
      const response = await fetch("/api/import", {
        method: "POST",
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      const conflictText = result.conflicts.length ? `，跳过 ${result.conflicts.length} 个同名文件` : "";
      await loadCatalog(true);
      const importedPaths = new Set((result.imported || []).map((path) => path.replaceAll("\\", "/").toLowerCase()));
      const importedMods = state.mods.filter((mod) => [
        ...(mod.vpkFiles || []),
        ...(mod.previewFiles || []),
      ].some((path) => importedPaths.has(path.replaceAll("\\", "/").toLowerCase())));
      return { result, conflictText, importedMods };
    });
    if (!importData) return;
    const { result, conflictText, importedMods } = importData;
    if (importedMods.length) {
      await openImportPreview(importedMods);
      activeImportMods = [];
      render();
    }
    showNotice(`已导入 ${result.imported.length} 个文件${conflictText}`, true);
  } catch (error) {
    showNotice(`导入失败：${error.message}`);
  }
}

function refreshCatalog() {
  if (operationBusy) return;
  return runExclusiveOperation("正在刷新目录，请稍候…", () => loadCatalog(true));
}

document.querySelector("#search-input").addEventListener("input", (event) => {
  if (operationBusy) return;
  state.search = event.target.value;
  render();
});
document.querySelector("#sort-select").addEventListener("change", (event) => {
  if (operationBusy) return;
  state.sort = event.target.value;
  render();
});
document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
  if (operationBusy) return;
  document.querySelectorAll(".filter").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  state.filter = button.dataset.filter;
  render();
}));
document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => {
  if (operationBusy) return;
  if (button.id === "ai-settings-nav") return;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  state.category = button.dataset.category;
  render();
}));
document.querySelectorAll(".sub-filter").forEach((button) => button.addEventListener("click", () => {
  if (operationBusy) return;
  document.querySelectorAll(".sub-filter").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  state.modelFilter = button.dataset.modelCategory;
  render();
}));
document.querySelectorAll("[data-bulk-action]").forEach((button) => button.addEventListener("click", () => {
  runBulkAction(button.dataset.bulkAction).catch((error) => showNotice(`批量操作失败：${error.message}`));
}));
document.querySelector("#clear-selection-button").addEventListener("click", () => {
  if (operationBusy) return;
  state.selectedIds.clear();
  render();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".card-title")) {
    document.querySelectorAll(".tag-menu").forEach((menu) => menu.classList.add("hidden"));
    document.querySelectorAll(".mod-card.menu-open").forEach((card) => card.classList.remove("menu-open"));
  }
});
aiDialogClose.addEventListener("click", () => aiDialog.close());
aiDialog.addEventListener("close", () => { activeAiMod = null; });
aiPromptSelect.addEventListener("change", () => {
  const prompt = selectedPrompt();
  aiPromptInput.value = prompt ? prompt.prompt : "";
  aiDeletePromptButton.disabled = aiPromptSelect.value === "default";
});
aiRunButton.addEventListener("click", () => runExclusiveOperation("正在进行 AI 分析，请稍候…", runAiAnalysis));
aiSavePromptButton.addEventListener("click", () => runExclusiveOperation("正在保存提示词，请稍候…", saveCurrentPrompt));
aiDeletePromptButton.addEventListener("click", () => runExclusiveOperation("正在删除提示词，请稍候…", deleteCurrentPrompt));
document.querySelector("#ai-settings-nav").addEventListener("click", openAiSettings);
document.querySelector("#settings-button").addEventListener("click", openAiSettings);
document.querySelector("#ai-settings-close").addEventListener("click", closeAiSettings);
document.querySelector("#ai-settings-save").addEventListener("click", () => runExclusiveOperation("正在保存 AI 设置，请稍候…", saveAiSettings));
document.querySelector("#ai-settings-clear").addEventListener("click", () => runExclusiveOperation("正在清除 API Key，请稍候…", clearAiKey));
document.querySelector("#refresh-button").addEventListener("click", refreshCatalog);
document.querySelector("#change-folder-button").addEventListener("click", changeFolder);
document.querySelector("#reset-folder-button").addEventListener("click", resetFolder);
document.querySelector("#refresh-button-top").addEventListener("click", refreshCatalog);
document.querySelector("#import-button").addEventListener("click", () => document.querySelector("#import-input").click());
document.querySelector("#import-input").addEventListener("change", (event) => {
  const [file] = event.target.files;
  if (file) importArchive(file);
  event.target.value = "";
});
document.addEventListener("click", (event) => {
  if (!operationBusy) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}, true);
importPreviewList.addEventListener("click", handleImportPreviewAction);
importPreviewClose.addEventListener("click", () => importPreviewDialog.close());
document.querySelector("#import-preview-done").addEventListener("click", () => importPreviewDialog.close());
vpkFilesList.addEventListener("click", handleVpkFileAction);
vpkFilesClose.addEventListener("click", () => vpkFilesDialog.close());
vpkFilesDialog.addEventListener("click", (event) => {
  if (event.target === vpkFilesDialog) vpkFilesDialog.close();
});
vpkFilesDialog.addEventListener("close", () => {
  delete vpkFilesDialog.dataset.modId;
});
nekoVpkTargetList.addEventListener("click", handleNekoVpkTargetAction);
nekoVpkClose.addEventListener("click", () => nekoVpkDialog.close());
nekoVpkDialog.addEventListener("click", (event) => {
  if (event.target === nekoVpkDialog) nekoVpkDialog.close();
});
nekoVpkDialog.addEventListener("close", () => {
  delete nekoVpkDialog.dataset.modId;
});
voiceInstall.addEventListener("click", () => handleVoiceAction("install"));
voiceRestore.addEventListener("click", () => handleVoiceAction("restore"));
voiceClose.addEventListener("click", () => voiceDialog.close());
voiceDialog.addEventListener("click", (event) => {
  if (event.target === voiceDialog && !operationBusy) voiceDialog.close();
});
voiceDialog.addEventListener("close", () => {
  delete voiceDialog.dataset.modId;
  setVoiceLoading(false);
});
document.addEventListener("keydown", (event) => {
  if (operationBusy) {
    event.preventDefault();
    event.stopImmediatePropagation();
    return;
  }
  if (event.key === "/" && document.activeElement.tagName !== "INPUT") {
    event.preventDefault();
    document.querySelector("#search-input").focus();
  }
});

if (window.lucide) lucide.createIcons();
loadCatalog();
checkForSourceChanges();
window.setInterval(checkForSourceChanges, 1000);
