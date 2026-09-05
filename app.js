const state = {
  mods: [], category: "all", roleSide: "survivor", voiceSide: "survivor", filter: "all", search: "", sort: "name", selectedIds: new Set(),
};

const NAV_ORDER_STORAGE_KEY = "l4d2-mod-manager.nav-order";
const THEME_STORAGE_KEY = "l4d2-mod-manager.theme";

const labels = {
  map: "地图",
  archive: "压缩包",
  spray: "喷漆",
  survivor_model: "生还者模型",
  infected_model: "感染者模型",
  weapon_model: "武器模型",
  prop_model: "环境模型",
  sound: "音效",
  voice_replacement: "语音替换",
  voice_manual: "手动替换语音",
  voice_automatic: "自动替换语音",
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
  archive: "压缩包 Mod",
  survivor_target: "模型",
  voice_replacement: "语音替换 Mod",
  spray: "喷漆 Mod",
};

const rootPath = document.querySelector("#root-path");
const shell = document.querySelector(".shell");
const sidebarToggleButton = document.querySelector("#settings-button");
const settingsNavButton = document.querySelector("#settings-nav");
const launchGameButton = document.querySelector("#launch-game-button");
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
const settingsPanel = document.querySelector("#settings-panel");
const aiModelSelect = document.querySelector("#ai-model-select");
const deepseekKeyInput = document.querySelector("#deepseek-key-input");
const settingsStatus = document.querySelector("#settings-status");
const themeSelect = document.querySelector("#theme-select");
const themeStatus = document.querySelector("#theme-status");
const updateAutoCheck = document.querySelector("#update-auto-check");
const updateCurrentVersion = document.querySelector("#update-current-version");
const updateCheckButton = document.querySelector("#update-check-button");
const updateInstallButton = document.querySelector("#update-install-button");
const updateStatus = document.querySelector("#update-status");
const importPreviewDialog = document.querySelector("#import-preview-dialog");
const importPreviewList = document.querySelector("#import-preview-list");
const importPreviewSummary = document.querySelector("#import-preview-summary");
const importPreviewStatus = document.querySelector("#import-preview-status");
const importPreviewClose = document.querySelector("#import-preview-close");
const workshopDialog = document.querySelector("#workshop-dialog");
const workshopSummary = document.querySelector("#workshop-summary");
const workshopList = document.querySelector("#workshop-list");
const workshopStatus = document.querySelector("#workshop-status");
const workshopSelectAll = document.querySelector("#workshop-select-all");
const workshopSelectedCount = document.querySelector("#workshop-selected-count");
const workshopCopy = document.querySelector("#workshop-copy");
const workshopClose = document.querySelector("#workshop-close");
const workshopLoading = document.querySelector("#workshop-loading");
const workshopLoadingMessage = document.querySelector("#workshop-loading-message");
const vpkFilesDialog = document.querySelector("#vpk-files-dialog");
const vpkFilesTitle = document.querySelector("#vpk-files-title");
const vpkFilesSummary = document.querySelector("#vpk-files-summary");
const vpkFilesNote = document.querySelector("#vpk-files-note");
const vpkFilesList = document.querySelector("#vpk-files-list");
const vpkFilesClose = document.querySelector("#vpk-files-close");
const sprayDialog = document.querySelector("#spray-dialog");
const spraySummary = document.querySelector("#spray-summary");
const spraySlotSummary = document.querySelector("#spray-slot-summary");
const spraySlotUsage = document.querySelector("#spray-slot-usage");
const sprayList = document.querySelector("#spray-list");
const sprayStatus = document.querySelector("#spray-status");
const sprayTabs = document.querySelectorAll(".spray-tab");
const sprayImportButton = document.querySelector("#spray-import-button");
const sprayImportInput = document.querySelector("#spray-import-input");
const sprayDropOverlay = document.querySelector("#spray-drop-overlay");
const sprayApply = document.querySelector("#spray-apply");
const sprayReset = document.querySelector("#spray-reset");
const sprayClose = document.querySelector("#spray-close");
const sprayLoading = document.querySelector("#spray-loading");
const sprayLoadingMessage = document.querySelector("#spray-loading-message");
const sprayConfigDialog = document.querySelector("#spray-config-dialog");
const sprayConfigSummary = document.querySelector("#spray-config-summary");
const sprayConfigBody = document.querySelector("#spray-config-body");
const sprayConfigStatus = document.querySelector("#spray-config-status");
const sprayConfigSave = document.querySelector("#spray-config-save");
const sprayConfigCancel = document.querySelector("#spray-config-cancel");
const sprayConfigClose = document.querySelector("#spray-config-close");
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
let workshopMods = [];
let workshopSelectedIds = new Set();
let sourceVersion = null;
let reloadRequested = false;
let activeAiMod = null;
let aiPrompts = { default: null, custom: [] };
let aiHistory = [];
let operationBusy = false;
let catalogLoaded = false;
let latestUpdateInfo = null;
let sprayAssets = [];
let sprayAssignments = {};
let spraySourceTab = "mod";
let sprayPendingPreviews = 0;
let sprayDragDepth = 0;
let sprayConfigAsset = null;
let sprayConfigDraft = null;
let sprayConfigPreviewTimer = null;
let sprayAssetsNeedRefresh = true;
const standardSpraySlots = Array.from({ length: 16 }, (_, index) => String(index + 1));
const SIDEBAR_STATE_STORAGE_KEY = "l4d2-mod-manager.sidebar-collapsed";

function setSidebarCollapsed(collapsed, persist = true) {
  shell.classList.toggle("sidebar-collapsed", collapsed);
  sidebarToggleButton.setAttribute("aria-pressed", String(collapsed));
  sidebarToggleButton.title = collapsed ? "显示左侧操作栏" : "隐藏左侧操作栏";
  sidebarToggleButton.setAttribute("aria-label", sidebarToggleButton.title);
  if (persist) localStorage.setItem(SIDEBAR_STATE_STORAGE_KEY, String(collapsed));
}

function toggleSidebar() {
  closeSettings();
  setSidebarCollapsed(!shell.classList.contains("sidebar-collapsed"));
}

function restoreSidebarState() {
  setSidebarCollapsed(localStorage.getItem(SIDEBAR_STATE_STORAGE_KEY) === "true", false);
}

function normalizeNavOrder(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value
    .filter((id) => typeof id === "string")
    .map((id) => id === "ai-settings" ? "settings" : id))];
}

function applyNavOrder(savedOrder) {
  const nav = document.querySelector(".nav");
  if (!nav) return;
  savedOrder = normalizeNavOrder(savedOrder);
  const items = new Map([...nav.querySelectorAll(".nav-item")].map((item) => [item.dataset.navId, item]));
  const orderedIds = [
    "library",
    ...savedOrder.filter((id) => id !== "library" && items.has(id)),
    ...[...items.keys()].filter((id) => id !== "library" && !savedOrder.includes(id)),
  ];
  orderedIds.forEach((id) => {
    const item = items.get(id);
    if (item) nav.appendChild(item);
  });
}

function readLocalNavOrder() {
  try {
    return normalizeNavOrder(JSON.parse(localStorage.getItem(NAV_ORDER_STORAGE_KEY) || "[]"));
  } catch {
    return [];
  }
}

function restoreNavOrder() {
  const savedOrder = readLocalNavOrder();
  applyNavOrder(savedOrder);
  return savedOrder;
}

async function restoreNavOrderFromServer(localOrder) {
  try {
    const response = await fetch("/api/navigation/order", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    const serverOrder = normalizeNavOrder(result.order);
    if (serverOrder.length) {
      applyNavOrder(serverOrder);
      localStorage.setItem(NAV_ORDER_STORAGE_KEY, JSON.stringify(serverOrder));
    } else if (localOrder.length) {
      await persistNavOrder(localOrder);
    }
  } catch {
    // Local order remains available when the settings endpoint is unavailable.
  }
}

async function persistNavOrder(order) {
  try {
    await fetch("/api/navigation/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order }),
    });
  } catch {
    // Keep the browser cache as a fallback for the current session.
  }
}

function saveNavOrder() {
  const nav = document.querySelector(".nav");
  if (!nav) return;
  const order = [...nav.querySelectorAll(".nav-item")].map((item) => item.dataset.navId).filter(Boolean);
  try {
    localStorage.setItem(NAV_ORDER_STORAGE_KEY, JSON.stringify(order));
  } catch {
    // Navigation still works when browser storage is unavailable.
  }
  persistNavOrder(order);
}

function initializeNavDragging() {
  const nav = document.querySelector(".nav");
  if (!nav) return;
  let draggedItem = null;
  let pressedItem = null;
  let pointerId = null;
  let pressTimer = null;
  let pressStart = null;
  let dragStarted = false;
  let suppressClickUntil = 0;

  const clearPressTimer = () => {
    if (pressTimer !== null) {
      window.clearTimeout(pressTimer);
      pressTimer = null;
    }
  };

  const clearDropTargets = () => {
    nav.querySelectorAll(".drop-target").forEach((item) => item.classList.remove("drop-target"));
  };

  const finishDrag = (event, cancelled = false) => {
    clearPressTimer();
    const item = draggedItem || pressedItem;
    if (dragStarted) {
      event?.preventDefault();
      suppressClickUntil = Date.now() + 500;
      if (!cancelled) saveNavOrder();
    }
    item?.classList.remove("drag-ready", "dragging");
    clearDropTargets();
    try {
      if (pointerId !== null && item?.hasPointerCapture(pointerId)) item.releasePointerCapture(pointerId);
    } catch {
      // Pointer capture may already have been released by the browser.
    }
    draggedItem = null;
    pressedItem = null;
    pointerId = null;
    pressStart = null;
    dragStarted = false;
  };

  const handlePointerMove = (event) => {
    if (pointerId !== event.pointerId || !pressedItem || !pressStart) return;
    const moved = Math.hypot(event.clientX - pressStart.x, event.clientY - pressStart.y);
    if (!draggedItem) {
      if (moved <= 8) return;
      clearPressTimer();
      draggedItem = pressedItem;
      dragStarted = true;
      draggedItem.classList.add("dragging");
    }
    if (!dragStarted) {
      if (moved < 6) return;
      dragStarted = true;
      draggedItem.classList.remove("drag-ready");
      draggedItem.classList.add("dragging");
    }
    event.preventDefault();
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest(".nav-item");
    clearDropTargets();
    if (!target || target.parentElement !== nav || target === draggedItem || target.classList.contains("nav-pinned")) return;
    target.classList.add("drop-target");
    const bounds = target.getBoundingClientRect();
    nav.insertBefore(draggedItem, event.clientY < bounds.top + bounds.height / 2 ? target : target.nextSibling);
  };

  nav.querySelectorAll(".nav-item").forEach((item) => {
    if (item.classList.contains("nav-pinned")) return;
    item.setAttribute("draggable", "false");
    item.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || pressedItem || pointerId !== null) return;
      pressedItem = item;
      pointerId = event.pointerId;
      pressStart = { x: event.clientX, y: event.clientY };
      try {
        item.setPointerCapture(pointerId);
      } catch {
        // Continue with window-level pointer events if capture is unavailable.
      }
      pressTimer = window.setTimeout(() => {
        if (pressedItem !== item || pointerId === null) return;
        draggedItem = item;
        item.classList.add("drag-ready");
      }, 260);
    });
    item.addEventListener("click", (event) => {
      if (Date.now() < suppressClickUntil) {
        event.preventDefault();
        event.stopImmediatePropagation();
        suppressClickUntil = 0;
      }
    });
  });
  window.addEventListener("pointermove", handlePointerMove, { passive: false });
  window.addEventListener("pointerup", (event) => {
    if (pointerId === event.pointerId) finishDrag(event);
  });
  window.addEventListener("pointercancel", (event) => {
    if (pointerId === event.pointerId) finishDrag(event, true);
  });
  window.addEventListener("blur", () => finishDrag(null, true));
}

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

function normalizeTheme(value) {
  return value === "light" ? "light" : "dark";
}

function applyTheme(theme, persist = true) {
  const normalized = normalizeTheme(theme);
  document.documentElement.dataset.theme = normalized;
  if (persist) localStorage.setItem(THEME_STORAGE_KEY, normalized);
  if (themeSelect) themeSelect.value = normalized;
  return normalized;
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

function voiceRoleSide(role) {
  if (role?.side === "infected" || role?.side === "survivor") return role.side;
  return ["boomer", "hunter", "smoker", "charger", "jockey", "spitter", "tank", "witch"].includes(role?.id)
    ? "infected"
    : "survivor";
}

function isSimpleInfectedVoice(mod) {
  const roles = mod.voiceRoles || [];
  return roles.some((role) => voiceRoleSide(role) === "infected")
    && !roles.some((role) => voiceRoleSide(role) === "survivor");
}

function visibleStatusLabel(mod) {
  const isVoiceReplacement = (mod.primaryCategories || []).includes("voice_replacement");
  if (isSimpleInfectedVoice(mod)) return statusLabels[mod.status] || "检测错误";
  const isAutomaticVoice = isVoiceReplacement
    && (mod.voiceModes || []).includes("automatic")
    && !(mod.voiceModes || []).includes("manual");
  if (isVoiceReplacement && !isAutomaticVoice) return mod.voiceInstalled === true ? "已替换" : "未替换";
  if (isAutomaticVoice) return mod.enabled === false ? "已停用" : "已启用";
  if ((mod.modelConflicts || []).length) return "模型冲突";
  if (mod.enabled === false && mod.vpkFiles?.length) return "已停用";
  return statusLabels[mod.status] || "检测错误";
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
      || (state.filter === "disabled" ? mod.enabled === false
        : state.filter === "conflict" ? (mod.modelConflicts || []).length > 0
          : mod.status === state.filter);
    const primaryCategories = effectivePrimaryCategories(mod);
    const modelCategoryBySide = {
      survivor: "survivor_model",
      infected: "infected_model",
      weapon: "weapon_model",
    };
    const hasConcreteModelTarget = state.roleSide === "weapon"
      ? (mod.weaponTargets || []).length > 0
      : (mod.characterTargets || []).some((target) => target.side === state.roleSide);
    const categoryMatch = state.category === "voice_replacement"
      ? primaryCategories.includes("voice_replacement")
        && (mod.voiceRoles || []).some((role) => voiceRoleSide(role) === state.voiceSide)
      : state.category === "all"
      || primaryCategories.includes(state.category)
      || (state.category === "survivor_target"
        && primaryCategories.includes(modelCategoryBySide[state.roleSide])
        && hasConcreteModelTarget);
    return filterMatch && categoryMatch && (!query || haystack.includes(query));
  });
  return filtered.sort((left, right) => {
    if (state.sort === "vpk") {
      const vpkDifference = right.vpkFiles.length - left.vpkFiles.length;
      if (vpkDifference) return vpkDifference;
    }
    if (state.sort === "status") {
      const statusDifference = visibleStatusLabel(left).localeCompare(visibleStatusLabel(right), "zh-CN");
      if (statusDifference) return statusDifference;
    }
    return left.name.localeCompare(right.name, "zh-CN");
  });
}

function renderStats() {
  const mods = visibleMods();
  const isFiltered = state.category !== "all"
    || state.filter !== "all"
    || state.search.trim() !== "";
  document.querySelector("#total-label").textContent = isFiltered ? "当前视图" : "全部 Mod";
  document.querySelector("#total-count").textContent = mods.length;
  document.querySelector("#matched-count").textContent = mods.filter((mod) => mod.status === "matched").length;
  document.querySelector("#issue-count").textContent = mods.filter((mod) => (
    mod.status !== "matched" || mod.errors.length || (mod.modelConflicts || []).length
  )).length;
}

function renderViewTitle() {
  const title = state.category === "survivor_target"
    ? (state.roleSide === "infected" ? "感染者模型" : state.roleSide === "weapon" ? "武器模型" : "生还者模型")
    : state.category === "voice_replacement"
    ? (state.voiceSide === "infected" ? "感染者语音替换" : "生还者语音替换")
    : (viewTitles[state.category] || viewTitles.all);
  document.querySelector("#page-title").textContent = title;
  document.querySelector("#spray-manager-button").classList.toggle("hidden", state.category !== "spray");
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
    const side = target.side === "survivor" ? "生还者" : "感染者";
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
  (mod.voiceRoles || []).forEach((role) => {
    addTag(`voice:${role.id}`, `语音替换 · ${role.name}`, primaryCategories.includes("voice_replacement"));
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
  const simpleInfectedVoice = isSimpleInfectedVoice(mod);
  const isSpray = (mod.primaryCategories || []).includes("spray");
  const isAutomaticVoice = isVoiceReplacement
    && (mod.voiceModes || []).includes("automatic")
    && !(mod.voiceModes || []).includes("manual");
  const voiceInstalled = mod.voiceInstalled === true;
  const disabled = mod.enabled === false && mod.vpkFiles.length > 0;
  const modelConflicts = mod.modelConflicts || [];
  const selected = state.selectedIds.has(mod.id);
  const status = simpleInfectedVoice
    ? (statusLabels[mod.status] || "检测错误")
    : isVoiceReplacement && !isAutomaticVoice
    ? (voiceInstalled ? "已替换" : "未替换")
    : (isAutomaticVoice ? (disabled ? "已停用" : "已启用") : (modelConflicts.length ? "模型冲突" : (disabled ? "已停用" : (statusLabels[mod.status] || "检测错误"))));
  const issue = mod.status !== "matched" || mod.errors.length > 0 || (isVoiceReplacement && !isAutomaticVoice && !simpleInfectedVoice && !voiceInstalled) || modelConflicts.length > 0;
  const hiddenTags = mod.hiddenTags || {};
  const tagItems = getTagItems(mod);
  const displayTagItems = state.category === "archive"
    ? tagItems.filter((item) => item.key === "category:archive")
    : tagItems;
  const tags = displayTagItems.map((item) => `<span class="tag ${item.primary ? "primary" : ""}">${escapeHtml(item.label)}</span>`).join("") || `<span class="tag">未分类</span>`;
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
  const conflictLine = modelConflicts.length
    ? `<div class="model-conflict-line" title="${escapeHtml(modelConflicts.map((item) => `${modelTargetLabel(item.target)}：${item.otherMods.join("、")}`).join("；"))}">模型冲突：${escapeHtml(modelConflicts.slice(0, 2).map((item) => `${modelTargetLabel(item.target)} 与 ${item.otherMods.join("、")}`).join("；"))}${modelConflicts.length > 2 ? "；…" : ""}</div>`
    : "";
  const nekoVpkTargets = mod.nekovpk?.targets || [];
  const hasExperimentalNekoVpkTargets = (mod.nekovpk?.mapping?.targets || []).some((target) => target.ready === true);
  const hasNekoVpkTargets = nekoVpkTargets.length > 1 || hasExperimentalNekoVpkTargets;
  const voiceActionLabel = isAutomaticVoice || simpleInfectedVoice ? "查看语音" : (voiceInstalled ? "恢复语音" : "安装语音");
  const voiceActionIcon = isAutomaticVoice || simpleInfectedVoice ? "eye" : (voiceInstalled ? "undo-2" : "mic-2");
  const voiceActionTitle = isAutomaticVoice || simpleInfectedVoice ? "查看自动加载的语音文件" : (voiceInstalled ? "恢复原始语音" : "安装语音替换");
  return `<article class="mod-card ${selected ? "selected" : ""}">
    <div class="preview ${mod.preview ? "" : "missing"}">
      ${preview}
    <span class="status-chip ${modelConflicts.length ? "model-conflict" : (isVoiceReplacement && !isAutomaticVoice && !simpleInfectedVoice ? (voiceInstalled ? "voice-installed" : "voice-uninstalled") : (disabled ? "disabled" : (issue ? "issue" : "")))}">${escapeHtml(status)}</span>
    </div>
    <div class="card-body">
      <div class="card-title"><label class="card-select" title="选择 ${escapeHtml(mod.name)}"><input class="card-select-input" type="checkbox" data-mod-id="${escapeHtml(mod.id)}" ${selected ? "checked" : ""} /><span class="sr-only">选择 ${escapeHtml(mod.name)}</span></label><h2 title="${escapeHtml(mod.name)}">${escapeHtml(mod.name)}</h2><button class="more-button" data-action="toggle-tag-menu" data-mod-id="${escapeHtml(mod.id)}" type="button" title="编辑标签" aria-label="编辑 ${escapeHtml(mod.name)} 的标签"><i data-lucide="more-horizontal"></i></button>${tagMenu}</div>
      <div class="tags">${tags}</div>
      <button class="vpk-line" data-action="show-vpk-files" data-mod-id="${escapeHtml(mod.id)}" type="button" title="查看关联的 VPK 文件" aria-label="查看 ${escapeHtml(mod.name)} 的关联 VPK 文件"><i data-lucide="package"></i><strong>${mod.vpkFiles.length}</strong> 个 VPK 文件<i class="vpk-line-arrow" data-lucide="chevron-right"></i></button>
      ${error}
      ${conflictLine}
      <div class="card-actions">
        ${mod.vpkFiles.length && (!isVoiceReplacement || simpleInfectedVoice) ? `<button class="card-action toggle-enabled" data-action="toggle-enabled" data-mod-id="${escapeHtml(mod.id)}" type="button" title="${disabled ? "启用 VPK 文件" : "停用 VPK 文件"}"><i data-lucide="${disabled ? "play" : "pause"}"></i>${disabled ? "启用" : "停用"}</button>` : ""}
        ${hasNekoVpkTargets ? `<button class="card-action" data-action="show-nekovpk" data-mod-id="${escapeHtml(mod.id)}" type="button" title="打开生还者角色替换"><i data-lucide="arrow-right-left"></i>替换角色</button>` : ""}
        ${isVoiceReplacement ? `<button class="card-action" data-action="show-voice" data-mod-id="${escapeHtml(mod.id)}" type="button" title="${voiceActionTitle}"><i data-lucide="${voiceActionIcon}"></i>${voiceActionLabel}</button>` : ""}
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
  const mappingTargets = (info.mapping?.targets || []).filter((target) => target.id !== info.currentTarget);
  nekoVpkTitle.textContent = `${mod.name} · 替换角色`;
  nekoVpkSummary.textContent = info.currentName
    ? `当前替换：${info.currentName}，可用预置角色 ${targets.length} 个`
    : `已发现 ${targets.length} 个可用预置角色`;
  const presetHtml = targets.length
    ? `<div class="nekovpk-section-label">作者预置资源</div>${targets.map((target) => {
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
    }).join("")}`
    : `<div class="vpk-files-empty">没有发现可用的角色资源</div>`;
  const mappingHtml = mappingTargets.length
    ? `<div class="nekovpk-section-label experimental">实验性角色替换 · 源角色：${escapeHtml(info.mapping?.sourceName || "未知")}</div>
      <p class="nekovpk-experimental-note">只改资源路径，不改模型骨骼；未通过游戏实测前请保留备份。</p>
      ${mappingTargets.map((target) => {
        const warnings = (target.warnings || []).join("；");
        const disabled = target.ready !== true;
        return `<button class="nekovpk-target experimental ${disabled ? "unavailable" : ""}" data-action="map-nekovpk" data-mod-id="${escapeHtml(mod.id)}" data-target-id="${escapeHtml(target.id)}" type="button" title="${escapeHtml(warnings)}" ${disabled ? "disabled" : ""}>
          <span class="nekovpk-target-icon"><i data-lucide="${disabled ? "alert-triangle" : "flask-conical"}"></i></span>
          <span class="nekovpk-target-info"><strong>替换为 ${escapeHtml(target.name)}</strong><span>${disabled ? escapeHtml(warnings) : `实验性替换 · ${target.fileCount} 个文件`}</span></span>
          <span class="nekovpk-target-state">${disabled ? "不可用" : "替换"}</span>
        </button>`;
      }).join("")}`
    : "";
  nekoVpkTargetList.innerHTML = presetHtml + mappingHtml;
  if (window.lucide) lucide.createIcons();
}

async function openNekoVpk(mod) {
  nekoVpkDialog.dataset.modId = mod.id;
  nekoVpkTitle.textContent = `${mod.name} · 替换角色`;
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
  const isAutomaticVoice = (mod.voiceModes || []).includes("automatic")
    && !(mod.voiceModes || []).includes("manual");
  const simpleInfectedVoice = isSimpleInfectedVoice(mod);
  const isManualOnly = info.manualOnly === true;
  voiceDialog.dataset.modId = mod.id;
  voiceTitle.textContent = `${mod.name} · 语音替换`;
  voiceSummary.textContent = isManualOnly
    ? `手动替换语音包 · VPK 内嵌 ${info.sourceArchiveCount || 0} 个压缩包`
    : isAutomaticVoice
    ? `标准 VPK 语音包 · 启用 VPK 后自动加载 · ${info.sourceFileCount} 个语音文件`
    : info.installed
    ? `已安装 · ${info.sourceFileCount} 个语音文件 · 可恢复原始语音`
    : `检测到 ${info.roles.length} 个角色、${info.sourceFileCount} 个语音文件`;
  const roleRows = (info.roles || []).map((role) => {
    const archiveRole = role.sourceType === "archive";
    const directories = isManualOnly
      ? `<span class="voice-directory missing">VPK 内嵌压缩包 · 需要按作者教程手动解压</span>`
      : isAutomaticVoice
      ? `<span class="voice-directory">VPK 内置路径 · 启用后自动加载</span>`
      : (role.targetDirectories || []).map((directory) =>
      `<span class="voice-directory">${escapeHtml(directory.root)} · 覆盖 ${directory.overwrite} / 新增 ${directory.new}</span>`
      ).join("");
    const missing = isManualOnly || isAutomaticVoice ? "" : (role.missingDirectories || []).map((directory) =>
      `<span class="voice-directory missing">缺少 ${escapeHtml(directory)}</span>`
    ).join("");
    const count = isManualOnly
      ? `<span>仅支持手动安装</span>`
      : isAutomaticVoice
      ? `<span>${role.sourceFileCount} 个文件</span>`
      : `<span>${role.overwriteCount} 覆盖</span><span>${role.newCount} 新增</span>`;
    const sourceLabel = archiveRole
      ? `${(role.archiveFiles || []).length} 个嵌套压缩包`
      : `${role.sourceFileCount} 个 WAV`;
    return `<div class="voice-role-row">
      <div class="voice-role-name"><strong>${escapeHtml(role.name)}</strong><span>${sourceLabel}</span></div>
      <div class="voice-role-targets">${directories || "<span class=\"voice-directory missing\">没有可安装的游戏目录</span>"}${missing}</div>
      <div class="voice-role-count">${count}</div>
    </div>`;
  }).join("");
  const missingRoots = (info.roles || []).flatMap((role) => role.missingDirectories || []);
  const conflictText = (info.conflicts || []).length
    ? `<div class="voice-warning">已有语音包生效：${escapeHtml(info.conflicts.map((item) => item.modName || item.modId).join("、"))}。安装时可选择替换。</div>`
    : "";
  const automaticNote = isAutomaticVoice
    ? `<div class="voice-auto-note">这是标准 VPK 语音包，不需要执行“安装语音”。启用 VPK 后，游戏会直接从这个 VPK 加载语音。</div>`
    : "";
  const manualNote = isManualOnly
    ? `<div class="voice-auto-note">这个包没有直接放入 WAV，而是把语音放在 VPK 内的压缩包中。管理器不会自动解压或修改游戏文件，请按作者教程手动处理。${(info.sourceFiles || []).map((file) => `<br /><code>${escapeHtml(file)}</code>`).join("")}</div>`
    : "";
  voiceBody.innerHTML = `${manualNote}${automaticNote}${conflictText}
    <div class="voice-summary-grid">
      <div><span>覆盖文件</span><strong>${info.roles.reduce((sum, role) => sum + role.overwriteCount, 0)}</strong></div>
      <div><span>新增文件</span><strong>${info.roles.reduce((sum, role) => sum + role.newCount, 0)}</strong></div>
      <div><span>${isManualOnly || isAutomaticVoice ? "加载方式" : "安装目录"}</span><strong>${isManualOnly ? "手动解压" : (isAutomaticVoice ? "VPK 自动加载" : info.roles.reduce((sum, role) => sum + role.targetDirectories.length, 0))}</strong></div>
      <div><span>${isManualOnly ? "内嵌压缩包" : (isAutomaticVoice ? "手动安装" : "缺失目录")}</span><strong>${isManualOnly ? (info.sourceArchiveCount || 0) : (isAutomaticVoice ? "不需要" : missingRoots.length)}</strong></div>
    </div>
    <div class="voice-role-list">${roleRows || `<div class="vpk-files-empty">没有发现可识别的语音角色</div>`}</div>`;
  voiceInstall.classList.toggle("hidden", isAutomaticVoice || isManualOnly || simpleInfectedVoice);
  voiceRestore.classList.toggle("hidden", isAutomaticVoice || isManualOnly || simpleInfectedVoice);
  voiceInstall.disabled = Boolean(info.installed) || !info.roles.some((role) => role.installable);
  voiceRestore.disabled = !info.installed;
  if (window.lucide) lucide.createIcons();
}

async function openVoiceReplacement(mod) {
  voiceDialog.dataset.modId = mod.id;
  voiceTitle.textContent = `${mod.name} · 语音替换`;
  voiceSummary.textContent = "正在读取语音包…";
  voiceBody.innerHTML = `<div class="vpk-files-empty">正在读取语音角色和目标目录…</div>`;
  voiceInstall.classList.remove("hidden");
  voiceRestore.classList.remove("hidden");
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
  const button = event.target.closest("button[data-action='convert-nekovpk'], button[data-action='map-nekovpk']");
  if (!button || button.disabled) return;
  const mod = state.mods.find((item) => item.id === button.dataset.modId);
  if (!mod) return;
  const targetName = button.querySelector("strong")?.textContent || "目标角色";
  const experimental = button.dataset.action === "map-nekovpk";
  if (experimental && !window.confirm(`将尝试把当前模型映射到“${targetName}”。这不会更改骨骼，可能出现姿势、材质或动画问题。确定继续吗？`)) return;
  return runExclusiveOperation(`${experimental ? "正在尝试映射" : "正在切换到"} ${targetName}，请稍候…`, async () => {
    button.disabled = true;
    nekoVpkLoading.classList.remove("hidden");
    nekoVpkLoading.querySelector(".operation-status span:last-child").textContent = `${experimental ? "正在尝试映射" : "正在切换到"} ${targetName}，请稍候…`;
    nekoVpkClose.disabled = true;
    nekoVpkTargetList.querySelectorAll("button").forEach((item) => { item.disabled = true; });
    try {
      const result = await postJson(experimental ? "/api/mod/nekovpk/map" : "/api/mod/nekovpk/convert", {
        id: mod.id,
        target: button.dataset.targetId,
      });
      await loadCatalog(true);
      nekoVpkDialog.close();
      showNotice(
        result.result?.changed === false
          ? `当前已经是“${targetName}”`
          : experimental
            ? `已尝试映射到“${targetName}”，请进入游戏测试模型、材质和动画`
            : `已切换到“${targetName}”`,
        true,
      );
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
  document.querySelector("#role-filters").classList.toggle("hidden", state.category !== "survivor_target");
  document.querySelector("#voice-role-filters").classList.toggle("hidden", state.category !== "voice_replacement");
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

function reportClientError(context, error) {
  const message = error instanceof Error ? error.message : String(error || "未知错误");
  fetch("/api/client-log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context: String(context).slice(0, 120), message: message.slice(0, 500) }),
    keepalive: true,
  }).catch(() => {});
}

function setSprayStatus(message, error = false) {
  sprayStatus.textContent = message;
  sprayStatus.classList.toggle("error", error);
}

function setSprayLoading(loading, message = "正在处理喷漆，请稍候…") {
  sprayLoading.classList.toggle("hidden", !loading);
  sprayLoadingMessage.textContent = message;
  sprayClose.disabled = loading;
  sprayImportButton.disabled = loading;
  sprayApply.disabled = loading;
}

function renderSpraySlotUsage() {
  const usedSlots = new Set(Object.keys(sprayAssignments).filter((slot) => standardSpraySlots.includes(slot)));
  spraySlotSummary.textContent = `已使用 ${usedSlots.size}/16，剩余 ${16 - usedSlots.size} 个`;
  spraySlotUsage.innerHTML = standardSpraySlots.map((slot) => {
    const assetId = sprayAssignments[slot];
    const asset = sprayAssets.find((item) => item.id === assetId);
    return `<button class="spray-slot-state ${asset ? "used" : ""}" data-spray-slot="${slot}" type="button" title="${asset ? `定位到${escapeHtml(asset.modName)}的喷漆素材` : "空闲槽位"}">
      <strong>槽位 ${slot}</strong><span>${asset ? escapeHtml(asset.modName) : "空闲"}</span>
    </button>`;
  }).join("");
}

function visibleSprayAssets() {
  return sprayAssets.filter((asset) => (spraySourceTab === "imported" ? asset.sourceType === "imported" : asset.sourceType !== "imported"));
}

function sprayConfigModeLabel(mode) {
  return { static: "静态", dynamic: "动态", gradient: "渐变" }[mode] || "未配置";
}

const sprayGradientLevels = [
  { label: "近距离", size: 512 },
  { label: "中近距离", size: 256 },
  { label: "中距离", size: 128 },
  { label: "中远距离", size: 64 },
  { label: "远距离", size: 32 },
];

function defaultSprayGradientMipmaps(assetId) {
  return sprayGradientLevels.map(({ size }) => ({ size, assetId, frame: 0 }));
}

function normalizedSprayGradientMipmaps(configuration, fallbackAssetId) {
  const raw = Array.isArray(configuration?.mipmaps) && configuration.mipmaps.length
    ? configuration.mipmaps
    : Array.isArray(configuration?.keyframes) && configuration.keyframes.length
      ? configuration.keyframes
      : [];
  return sprayGradientLevels.map(({ size }, index) => {
    const item = raw[index] || raw[raw.length - 1] || {};
    return {
      size,
      assetId: item.assetId || fallbackAssetId,
      frame: Number.isInteger(item.frame) ? item.frame : 0,
    };
  });
}

function defaultSprayConfig(asset) {
  return { mode: "static", frame: 0, source: "images", frames: [{ assetId: asset.id, frame: 0, durationMs: 100 }], mipmaps: defaultSprayGradientMipmaps(asset.id) };
}

function importedSprayAssets() {
  return sprayAssets.filter((asset) => asset.sourceType === "imported");
}

function sprayPreviewUrl(assetId, frame = null) {
  const asset = sprayAssets.find((item) => item.id === assetId);
  if (!asset) return "";
  return frame === null ? asset.preview : `${asset.preview}&frame=${encodeURIComponent(frame)}`;
}

function stopSprayConfigPreview() {
  if (sprayConfigPreviewTimer !== null) {
    window.clearTimeout(sprayConfigPreviewTimer);
    sprayConfigPreviewTimer = null;
  }
}

function renderSprayConfigPreview() {
  const stage = sprayConfigBody.querySelector("#spray-config-preview-stage");
  const caption = sprayConfigBody.querySelector("#spray-config-preview-caption");
  if (!stage || !caption || !sprayConfigAsset) return;
  stopSprayConfigPreview();
  const configuration = collectSprayConfig();
  const image = (assetId, frame = 0) => {
    const source = sprayPreviewUrl(assetId, frame);
    return source ? `<img class="spray-config-preview-image" src="${escapeHtml(source)}" alt="" />` : "";
  };
  if (configuration.mode === "static") {
    stage.dataset.previewKind = "static";
    stage.innerHTML = image(sprayConfigAsset.id, configuration.frame) || `<span>暂无可用预览</span>`;
    caption.textContent = `静态 · 第 ${configuration.frame || 0} 帧`;
    return;
  }
  if (configuration.mode === "dynamic" && configuration.source === "gif") {
    const frameCount = Math.max(1, Math.min(16, Number(sprayConfigAsset.frameCount) || 1));
    const duration = Math.max(20, Number(configuration.frameDurationMs) || 100);
    stage.dataset.previewKind = "dynamic";
    stage.innerHTML = Array.from({ length: frameCount }, (_, frame) => image(sprayConfigAsset.id, frame)).join("") || `<span>暂无可用预览</span>`;
    const images = [...stage.querySelectorAll(".spray-config-preview-image")];
    let index = 0;
    const showNext = () => {
      images.forEach((item, imageIndex) => item.classList.toggle("active", imageIndex === index));
      index = (index + 1) % images.length;
      sprayConfigPreviewTimer = window.setTimeout(showNext, duration);
    };
    if (images.length) showNext();
    caption.textContent = `动态 · GIF ${frameCount} 帧 · 每帧 ${duration} 毫秒`;
    return;
  }
  if (configuration.mode === "gradient") {
    const levels = normalizedSprayGradientMipmaps(configuration, sprayConfigAsset.id);
    const items = levels
      .map((item, index) => ({ item, level: sprayGradientLevels[index], asset: sprayAssets.find((asset) => asset.id === item.assetId) }))
      .filter(({ asset }) => asset);
    stage.dataset.previewKind = "gradient";
    if (!items.length) {
      stage.innerHTML = `<span>请选择渐变图片</span>`;
      caption.textContent = "渐变 · 尚未配置距离图片";
      return;
    }
    stage.innerHTML = `<div class="spray-gradient-preview-grid">${items.map(({ item, level, asset }) => `
      <div class="spray-gradient-preview-item">
        <div class="spray-gradient-preview-frame">${image(asset.id, item.frame)}</div>
        <span>${level.size}×${level.size}</span>
      </div>`).join("")}</div>`;
    caption.textContent = "渐变 · 游戏根据距离自动切换 5 级图片";
    return;
  }
  const items = configuration.frames;
  const assets = items.map((item) => ({ item, asset: sprayAssets.find((asset) => asset.id === item.assetId) })).filter(({ asset }) => asset);
  if (!assets.length) {
    stage.dataset.previewKind = configuration.mode;
    stage.innerHTML = `<span>${configuration.mode === "gradient" ? "请选择至少两张关键帧" : "请选择至少一张图片"}</span>`;
    caption.textContent = configuration.mode === "gradient" ? "渐变 · 尚未选择关键帧" : "动态 · 尚未选择图片";
    return;
  }
  stage.dataset.previewKind = configuration.mode;
  stage.innerHTML = assets.map(({ item, asset }) => image(asset.id, 0)).join("");
  const images = [...stage.querySelectorAll(".spray-config-preview-image")];
  let index = 0;
  const showNext = () => {
    images.forEach((item, imageIndex) => item.classList.toggle("active", imageIndex === index));
    const duration = Math.max(20, Number(assets[index].item.durationMs) || 100);
    index = (index + 1) % images.length;
    sprayConfigPreviewTimer = window.setTimeout(showNext, duration);
  };
  showNext();
  caption.textContent = configuration.mode === "gradient"
    ? `渐变 · ${assets.length} 张关键帧 · 每帧 ${Math.max(20, Number(configuration.frameDurationMs) || 80)} 毫秒`
    : `动态 · ${assets.length} 张图片 · 按各自时长播放`;
}

function renderSprayConfigEditor() {
  if (!sprayConfigAsset || !sprayConfigDraft) return;
  const mode = sprayConfigDraft.mode || "static";
  const assets = importedSprayAssets();
  const isGif = sprayConfigAsset.filename.toLowerCase().endsWith(".gif");
  const selectedFrames = new Map((sprayConfigDraft.frames || []).map((item) => [item.assetId, item]));
  const selectedMipmaps = normalizedSprayGradientMipmaps(sprayConfigDraft, sprayConfigAsset.id);
  sprayConfigSummary.textContent = `${sprayConfigAsset.filename} · 原始文件保留不变`;
  sprayConfigBody.innerHTML = `
    <div class="spray-config-mode" role="tablist" aria-label="喷漆配置模式">
      ${["static", "dynamic", "gradient"].map((item) => `<button class="spray-config-mode-button ${mode === item ? "active" : ""}" data-config-mode="${item}" type="button">${sprayConfigModeLabel(item)}</button>`).join("")}
    </div>
    <section class="spray-config-preview" aria-label="喷漆效果预览">
      <div class="spray-config-preview-head"><strong>效果预览</strong><span id="spray-config-preview-caption"></span></div>
      <div id="spray-config-preview-stage" class="spray-config-preview-stage" role="img" aria-label="当前喷漆效果预览"></div>
    </section>
    ${mode === "static" ? `
      <section class="spray-config-section">
        <div class="spray-config-section-head"><strong>静态画面</strong><span>普通图片只有第 0 帧</span></div>
        <label class="spray-config-field">使用 GIF 的第几帧
          <input id="spray-config-static-frame" class="settings-input" type="number" min="0" max="63" value="${Number.isInteger(sprayConfigDraft.frame) ? sprayConfigDraft.frame : 0}" ${isGif ? "" : "disabled"} />
        </label>
      </section>` : ""}
    ${mode === "dynamic" ? `
      <section class="spray-config-section">
        <div class="spray-config-section-head"><strong>动态来源</strong><span>游戏内按统一帧速播放</span></div>
        <div class="spray-config-source-tabs">
          ${isGif ? `<label><input type="radio" name="spray-config-source" value="gif" ${sprayConfigDraft.source === "gif" ? "checked" : ""} />当前 GIF 全部帧</label>` : ""}
          <label><input type="radio" name="spray-config-source" value="images" ${sprayConfigDraft.source !== "gif" ? "checked" : ""} />拼接多张导入图</label>
        </div>
        ${sprayConfigDraft.source === "gif" && isGif ? `
          <label class="spray-config-field">每帧时长（毫秒）
            <input id="spray-config-gif-duration" class="settings-input" type="number" min="20" max="5000" value="${sprayConfigDraft.frameDurationMs || 100}" />
          </label>` : `
          <div class="spray-config-image-list">
            ${assets.map((asset) => {
              const item = selectedFrames.get(asset.id);
              return `<label class="spray-config-image-row"><input type="checkbox" data-config-frame-asset="${escapeHtml(asset.id)}" ${item ? "checked" : ""} /><img src="${asset.preview}" alt="" loading="lazy" /><span title="${escapeHtml(asset.filename)}">${escapeHtml(asset.filename)}</span><input class="settings-input spray-config-duration" data-config-duration="${escapeHtml(asset.id)}" type="number" min="20" max="5000" value="${item?.durationMs || 100}" ${item ? "" : "disabled"} /></label>`;
            }).join("")}
          </div>`}
      </section>` : ""}
    ${mode === "gradient" ? `
      <section class="spray-config-section">
        <div class="spray-config-section-head"><strong>距离图片</strong><span>游戏会按喷漆距离自动选择</span></div>
        <div class="spray-gradient-mipmap-list">
          ${sprayGradientLevels.map((level, index) => {
            const selected = selectedMipmaps[index];
            const selectedAsset = assets.find((asset) => asset.id === selected.assetId) || sprayConfigAsset;
            return `<label class="spray-gradient-mipmap-row">
              <span class="spray-gradient-mipmap-label"><strong>${level.label}</strong><small>${level.size}×${level.size}</small></span>
              <span class="spray-gradient-mipmap-thumb"><img src="${selectedAsset.preview}" alt="" loading="lazy" /></span>
              <select class="settings-input spray-gradient-mipmap-select" data-config-mipmap="${index}" aria-label="${level.label}使用的图片">
                ${assets.map((asset) => `<option value="${escapeHtml(asset.id)}" ${asset.id === selected.assetId ? "selected" : ""}>${escapeHtml(asset.filename)}</option>`).join("")}
              </select>
            </label>`;
          }).join("")}
        </div>
      </section>` : ""}
    <p class="spray-config-note">保存配置后仍需点击“应用组合喷漆”才会写入游戏 VPK。</p>`;
  renderSprayConfigPreview();
  if (window.lucide) lucide.createIcons();
}

function collectSprayConfig() {
  const mode = sprayConfigBody.querySelector("[data-config-mode].active")?.dataset.configMode || "static";
  if (mode === "static") {
    return { mode, frame: Number(sprayConfigBody.querySelector("#spray-config-static-frame")?.value || 0) };
  }
  if (mode === "dynamic") {
    const source = sprayConfigBody.querySelector("input[name='spray-config-source']:checked")?.value || "images";
    if (source === "gif") {
      return { mode, source, assetId: sprayConfigAsset.id, frameDurationMs: Number(sprayConfigBody.querySelector("#spray-config-gif-duration")?.value || 100) };
    }
    return {
      mode,
      source,
      frames: [...sprayConfigBody.querySelectorAll("input[data-config-frame-asset]:checked")].map((input) => ({
        assetId: input.dataset.configFrameAsset,
        frame: 0,
        durationMs: Number(sprayConfigBody.querySelector(`[data-config-duration='${CSS.escape(input.dataset.configFrameAsset)}']`)?.value || 100),
      })),
    };
  }
  return {
    mode,
    mipmaps: [...sprayConfigBody.querySelectorAll("select[data-config-mipmap]")].map((select, index) => ({
      size: sprayGradientLevels[index]?.size,
      assetId: select.value,
      frame: 0,
    })),
  };
}

function openSprayConfig(assetId) {
  if (operationBusy) return;
  const asset = sprayAssets.find((item) => item.id === assetId && item.sourceType === "imported");
  if (!asset) return;
  sprayConfigAsset = asset;
  sprayConfigDraft = JSON.parse(JSON.stringify(asset.configuration || defaultSprayConfig(asset)));
  renderSprayConfigEditor();
  if (typeof sprayConfigDialog.showModal === "function") sprayConfigDialog.showModal();
  else sprayConfigDialog.setAttribute("open", "");
}

async function saveSprayConfig() {
  if (!sprayConfigAsset || operationBusy) return;
  const configuration = collectSprayConfig();
  return runExclusiveOperation("正在保存喷漆配置，请稍候…", async () => {
    sprayConfigSave.disabled = true;
    try {
      const result = await postJson("/api/spray/config", { assetId: sprayConfigAsset.id, configuration });
      const asset = sprayAssets.find((item) => item.id === sprayConfigAsset.id);
      if (asset) asset.configuration = result.configuration;
      renderSprayAssets();
      sprayConfigDialog.close();
      showNotice(`已保存“${sprayConfigAsset.filename}”的${sprayConfigModeLabel(result.configuration.mode)}配置`, true);
    } catch (error) {
      sprayConfigStatus.textContent = `保存失败：${error.message}`;
      sprayConfigStatus.classList.add("error");
    } finally {
      sprayConfigSave.disabled = false;
    }
  });
}

function renderSprayAssets() {
  const options = [
    `<option value="">不应用</option>`,
    ...standardSpraySlots.map((slot) => `<option value="${slot}">槽位 ${slot}</option>`),
  ].join("");
  renderSpraySlotUsage();
  const assets = visibleSprayAssets();
  if (!assets.length) {
    sprayList.innerHTML = `<div class="spray-empty-drop"><i data-lucide="image-plus"></i><strong>${spraySourceTab === "imported" ? "还没有导入图片" : "没有检测到可预览的 Mod 喷漆素材"}</strong></div>`;
    if (window.lucide) lucide.createIcons();
    return;
  }
  sprayList.innerHTML = assets.map((asset) => {
    const selectedSlot = Object.entries(sprayAssignments).find(([, assetId]) => assetId === asset.id)?.[0] || "";
    const configuration = asset.configuration;
    return `<article class="spray-asset">
      <div class="spray-asset-image"><img src="${asset.preview}" data-spray-preview="true" alt="${escapeHtml(asset.modName)} 槽位 ${escapeHtml(asset.sourceSlot)}" loading="lazy" /></div>
      <div class="spray-asset-info"><div class="spray-asset-info-head"><strong title="${escapeHtml(asset.modName)}">${escapeHtml(asset.modName)}</strong>${asset.sourceType === "imported" ? `<button class="spray-asset-config" data-spray-config="${escapeHtml(asset.id)}" type="button" title="配置导入喷漆" aria-label="配置 ${escapeHtml(asset.filename)}"><i data-lucide="settings-2"></i></button><button class="spray-asset-delete" data-spray-delete="${escapeHtml(asset.id)}" type="button" title="将导入图片移入回收站" aria-label="将 ${escapeHtml(asset.filename)} 移入回收站"><i data-lucide="trash-2"></i></button>` : ""}</div><span title="${escapeHtml(asset.vpkPath)}">${asset.sourceType === "imported" ? `导入图片 · ${escapeHtml(asset.filename)}${configuration ? ` · ${sprayConfigModeLabel(configuration.mode)}` : ""}` : `原槽位 ${escapeHtml(asset.sourceSlot)} · ${escapeHtml(asset.filename)}`}</span></div>
      <select class="spray-asset-slot" data-spray-asset="${escapeHtml(asset.id)}" aria-label="为该喷漆选择目标槽位">${options.replace(`value="${selectedSlot}"`, `value="${selectedSlot}" selected`)}</select>
    </article>`;
  }).join("");
  sprayPendingPreviews = 0;
  setSprayStatus("预览按需加载，滚动到素材时读取图片。", false);
  if (window.lucide) lucide.createIcons();
}

function setSpraySourceTab(source) {
  spraySourceTab = source === "imported" ? "imported" : "mod";
  sprayTabs.forEach((tab) => {
    const active = tab.dataset.spraySource === spraySourceTab;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  renderSprayAssets();
}

function focusSprayAsset(slot) {
  const assetId = sprayAssignments[slot];
  const asset = sprayAssets.find((item) => item.id === assetId);
  if (!asset) return;
  setSpraySourceTab(asset.sourceType === "imported" ? "imported" : "mod");
  window.setTimeout(() => {
    const card = [...sprayList.querySelectorAll("[data-spray-asset]")]
      .find((item) => item.dataset.sprayAsset === asset.id);
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("spray-asset-focused");
    window.setTimeout(() => card.classList.remove("spray-asset-focused"), 1400);
  }, 0);
}

function updateSpraySummary() {
  const modAssets = sprayAssets.filter((asset) => asset.sourceType !== "imported");
  const importedAssets = sprayAssets.filter((asset) => asset.sourceType === "imported");
  spraySummary.textContent = `共 ${sprayAssets.length} 张素材（Mod ${modAssets.length} 张，导入 ${importedAssets.length} 张）；可配置 16 个标准槽位`;
}

function handleSprayPreviewEvent(event) {
  if (!event.target.matches("img[data-spray-preview]")) return;
  sprayPendingPreviews = Math.max(0, sprayPendingPreviews - 1);
  if (sprayPendingPreviews === 0) setSprayStatus("图片提取完成，请为素材指定目标槽位。", false);
}

async function openSprayManager() {
  if (operationBusy) return;
  const loadingMessage = sprayAssetsNeedRefresh
    ? "正在提取喷漆图片，首次加载可能较慢…"
    : "正在读取已缓存的喷漆素材…";
  setSprayStatus(loadingMessage);
  sprayList.innerHTML = `<div class="vpk-files-empty">${loadingMessage}</div>`;
  if (typeof sprayDialog.showModal === "function") sprayDialog.showModal();
  else sprayDialog.setAttribute("open", "");
  try {
    const route = sprayAssetsNeedRefresh ? "/api/spray/assets?refresh=1" : "/api/spray/assets";
    const response = await fetch(route, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    sprayAssets = result.assets || [];
    sprayAssignments = { ...(result.assignments || {}) };
    const assetIds = new Set(sprayAssets.map((asset) => asset.id));
    sprayAssignments = Object.fromEntries(Object.entries(sprayAssignments).filter(([slot, id]) => standardSpraySlots.includes(slot) && assetIds.has(id)));
    sprayAssetsNeedRefresh = false;
    updateSpraySummary();
    setSpraySourceTab(spraySourceTab);
  } catch (error) {
    setSprayStatus(`读取喷漆失败：${error.message}`, true);
    sprayList.innerHTML = `<div class="vpk-files-empty">喷漆素材读取失败</div>`;
  }
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

async function importSprayImages(files) {
  const selectedFiles = [...files];
  if (!selectedFiles.length) return;
  return runExclusiveOperation(`正在导入 ${selectedFiles.length} 张图片，请稍候…`, async () => {
    setSprayLoading(true, `正在导入 ${selectedFiles.length} 张图片，请稍候…`);
    try {
      const images = [];
      for (const file of selectedFiles) {
        images.push({ name: file.name, data: arrayBufferToBase64(await file.arrayBuffer()) });
      }
      const result = await postJson("/api/spray/import", { images });
      sprayAssetsNeedRefresh = true;
      const response = await fetch("/api/spray/assets?refresh=1", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      sprayAssets = payload.assets || [];
      sprayAssetsNeedRefresh = false;
      sprayAssignments = { ...(payload.assignments || {}) };
      updateSpraySummary();
      setSpraySourceTab("imported");
      const details = [];
      if (result.skipped?.length) details.push(`跳过 ${result.skipped.length} 张重复图片`);
      showNotice(`已导入 ${result.imported?.length || 0} 张图片${details.length ? `，${details.join("，")}` : ""}`, true);
    } catch (error) {
      setSprayStatus(`导入图片失败：${error.message}`, true);
      showNotice(`导入图片失败：${error.message}`);
    } finally {
      setSprayLoading(false);
    }
  });
}

function hasDraggedFiles(event) {
  return [...(event.dataTransfer?.types || [])].includes("Files");
}

function setSprayDropActive(active) {
  sprayDropOverlay.classList.toggle("hidden", !active);
  sprayDialog.classList.toggle("spray-drop-active", active);
}

function handleSpraySelection(event) {
  const select = event.target.closest(".spray-asset-slot");
  if (!select) return;
  const assetId = select.dataset.sprayAsset;
  Object.keys(sprayAssignments).forEach((slot) => {
    if (sprayAssignments[slot] === assetId) delete sprayAssignments[slot];
  });
  if (select.value) {
    Object.keys(sprayAssignments).forEach((slot) => {
      if (slot === select.value) delete sprayAssignments[slot];
    });
    sprayAssignments[select.value] = assetId;
  }
  renderSprayAssets();
  setSprayStatus(`已选择 ${Object.keys(sprayAssignments).length} 个喷漆槽位。`);
}

async function deleteImportedSpray(assetId) {
  if (operationBusy) return;
  const asset = sprayAssets.find((item) => item.id === assetId && item.sourceType === "imported");
  if (!asset) return;
  if (!window.confirm(`确定将“${asset.filename}”移入回收站吗？\n如果它已配置到槽位，相关使用记录也会被清除。`)) return;
  return runExclusiveOperation("正在删除导入喷漆，请稍候…", async () => {
    setSprayLoading(true, "正在将导入喷漆移入回收站，请稍候…");
    try {
      const result = await postJson("/api/spray/delete", { assetId });
      sprayAssets = sprayAssets.filter((item) => item.id !== assetId);
      (result.clearedSlots || []).forEach((slot) => delete sprayAssignments[slot]);
      updateSpraySummary();
      renderSprayAssets();
      const slotMessage = result.clearedSlots?.length ? `，已清除槽位 ${result.clearedSlots.join("、")}` : "";
      showNotice(`已将“${asset.filename}”移入回收站${slotMessage}`, true);
    } catch (error) {
      setSprayStatus(`删除喷漆失败：${error.message}`, true);
      showNotice(`删除喷漆失败：${error.message}`);
    } finally {
      setSprayLoading(false);
    }
  });
}

function handleSprayListClick(event) {
  const configButton = event.target.closest("button[data-spray-config]");
  if (configButton) {
    openSprayConfig(configButton.dataset.sprayConfig);
    return;
  }
  const button = event.target.closest("button[data-spray-delete]");
  if (button) deleteImportedSpray(button.dataset.sprayDelete).catch((error) => showNotice(`删除喷漆失败：${error.message}`));
}

async function applySprayCollection() {
  const count = Object.keys(sprayAssignments).length;
  if (!count) {
    setSprayStatus("请至少为一个槽位选择喷漆。", true);
    return;
  }
  return runExclusiveOperation("正在生成组合喷漆，请稍候…", async () => {
    setSprayLoading(true, "正在生成组合喷漆，请稍候…");
    try {
      const result = await postJson("/api/spray/apply", { assignments: sprayAssignments });
      await loadCatalog();
      sprayDialog.close();
      const looseMessage = result.looseFilesMoved?.length
        ? `，已备份并移出 ${result.looseFilesMoved.length} 个散装喷漆文件`
        : "";
      showNotice(`已生成组合喷漆，共配置 ${count} 个槽位；原始喷漆 Mod 已停用${looseMessage}`, true);
    } catch (error) {
      setSprayStatus(`应用喷漆失败：${error.message}`, true);
      showNotice(`应用喷漆失败：${error.message}`);
    } finally {
      setSprayLoading(false);
    }
  });
}

async function resetSprayUsage() {
  if (!window.confirm("确定清除最近一次保存的自定义喷漆配置吗？\n这不会删除或停用任何 VPK 文件。")) return;
  return runExclusiveOperation("正在重置喷漆使用情况，请稍候…", async () => {
    sprayReset.disabled = true;
    try {
      await postJson("/api/spray/reset", {});
      sprayAssignments = {};
      renderSprayAssets();
      setSprayStatus("已清除最近一次保存的自定义喷漆配置。", false);
      showNotice("已重置喷漆使用情况", true);
    } catch (error) {
      setSprayStatus(`重置喷漆失败：${error.message}`, true);
    } finally {
      sprayReset.disabled = false;
    }
  });
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

function modelTargetKey(target) {
  return `${target.side || ""}:${target.id || ""}`;
}

function modelTargetLabel(target) {
  const side = target.side === "survivor" ? "生还者" : target.side === "weapon" ? "武器" : "感染者";
  return `${side} · ${target.name}`;
}

function refreshModelConflictState() {
  const groups = new Map();
  const enabledMods = state.mods.filter((mod) => mod.enabled !== false && mod.vpkFiles?.length);
  for (const mod of enabledMods) {
    const seenTargets = new Set();
    for (const target of getModelTargets(mod)) {
      const key = modelTargetKey(target);
      if (seenTargets.has(key)) continue;
      seenTargets.add(key);
      if (!groups.has(key)) groups.set(key, { target, mods: [] });
      groups.get(key).mods.push(mod);
    }
  }

  state.mods.forEach((mod) => { mod.modelConflicts = []; });
  for (const group of groups.values()) {
    if (group.mods.length < 2) continue;
    for (const mod of group.mods) {
      mod.modelConflicts.push({
        target: group.target,
        otherMods: group.mods.filter((candidate) => candidate.id !== mod.id).map((candidate) => candidate.name),
      });
    }
  }
}

function getModelTargets(mod) {
  const primaryCategories = effectivePrimaryCategories(mod);
  const characterTargets = (mod.characterTargets || []).filter((target) => (
    (target.side === "survivor" && primaryCategories.includes("survivor_model"))
    || (target.side === "infected" && primaryCategories.includes("infected_model"))
  ));
  const weaponTargets = primaryCategories.includes("weapon_model")
    ? (mod.weaponTargets || []).map((target) => ({ ...target, side: "weapon" }))
    : [];
  return [
    ...characterTargets,
    ...weaponTargets,
  ].filter((target) => target.side && target.id);
}

function findEnableConflicts(modsToEnable) {
  const selectedIds = new Set(modsToEnable.map((mod) => mod.id));
  const conflicts = [];
  const seen = new Set();
  const addConflict = (target, first, second, reason) => {
    const pair = [first.id, second.id].sort().join("|");
    const key = `${pair}:${modelTargetKey(target)}`;
    if (seen.has(key)) return;
    seen.add(key);
    conflicts.push({ target, first, second, reason });
  };

  for (const mod of modsToEnable) {
    for (const target of getModelTargets(mod)) {
      for (const other of state.mods) {
        if (other.id === mod.id || selectedIds.has(other.id) || other.enabled === false || !other.vpkFiles?.length) continue;
        if (getModelTargets(other).some((candidate) => modelTargetKey(candidate) === modelTargetKey(target))) {
          addConflict(target, mod, other, "已有启用的 Mod");
        }
      }
    }
  }

  for (let index = 0; index < modsToEnable.length; index += 1) {
    for (let next = index + 1; next < modsToEnable.length; next += 1) {
      const first = modsToEnable[index];
      const second = modsToEnable[next];
      for (const target of getModelTargets(first)) {
        if (getModelTargets(second).some((candidate) => modelTargetKey(candidate) === modelTargetKey(target))) {
          addConflict(target, first, second, "本次将同时启用");
        }
      }
    }
  }
  return conflicts;
}

function confirmEnableConflicts(modsToEnable) {
  const conflicts = findEnableConflicts(modsToEnable);
  if (!conflicts.length) return true;
  const lines = conflicts.slice(0, 8).map(({ target, first, second, reason }) =>
    `- ${modelTargetLabel(target)}：${first.name} / ${second.name}（${reason}）`
  );
  const extra = conflicts.length > lines.length ? `\n另有 ${conflicts.length - lines.length} 个重复目标未展开。` : "";
  return window.confirm(
    `检测到启用后可能发生模型覆盖：\n${lines.join("\n")}${extra}\n\n后启用的 Mod 可能覆盖前一个 Mod 的模型。仍要继续吗？`
  );
}

async function runBulkAction(action) {
  if (operationBusy) return;
  const ids = [...state.selectedIds];
  if (!ids.length) return;
  if (action === "delete" && !window.confirm(`确定将选中的 ${ids.length} 个 Mod 移入回收站吗？\n之后可从系统回收站恢复。`)) return;
  if (action === "enable") {
    const modsToEnable = state.mods.filter((mod) => ids.includes(mod.id) && mod.enabled === false);
    if (!confirmEnableConflicts(modsToEnable)) return;
  }
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

async function getUpdateConfig() {
  const response = await fetch("/api/update/config", { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

async function getThemeConfig() {
  const response = await fetch("/api/theme/config", { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

async function initializeTheme() {
  // Use the server setting as the source of truth; localStorage is only a fast fallback.
  applyTheme(normalizeTheme(localStorage.getItem(THEME_STORAGE_KEY)), false);
  try {
    const config = await getThemeConfig();
    applyTheme(config.theme, true);
  } catch {
    // Keep the locally cached theme when the backend is temporarily unavailable.
  }
}

async function checkForUpdates({ automatic = false } = {}) {
  if (!automatic) {
    updateStatus.textContent = "正在检查更新…";
  }
  try {
    const response = await fetch(`/api/update/check?time=${Date.now()}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    latestUpdateInfo = result;
    updateCurrentVersion.textContent = `v${result.currentVersion}`;
    updateInstallButton.classList.toggle("hidden", !result.updateAvailable);
    if (result.updateAvailable) {
      updateStatus.textContent = `发现新版本 v${result.latestVersion}`;
      if (automatic) showNotice(`发现新版本 v${result.latestVersion}，请打开设置进行更新`);
    } else {
      updateStatus.textContent = `当前已是最新版本 v${result.currentVersion}`;
    }
    return result;
  } catch (error) {
    if (!automatic) updateStatus.textContent = `检查失败：${error.message}`;
    return null;
  }
}

async function saveUpdateCheckSetting(enabled) {
  const result = await postJson("/api/update/config", { autoCheck: enabled });
  updateAutoCheck.checked = result.autoCheck;
  updateStatus.textContent = result.autoCheck ? "已开启启动时自动检查" : "已关闭启动时自动检查";
}

async function installUpdate() {
  if (!latestUpdateInfo || !latestUpdateInfo.updateAvailable) {
    await checkForUpdates();
    return;
  }
  updateStatus.textContent = "正在下载并准备更新，请稍候…";
  const result = await postJson("/api/update/install", {});
  if (!result.restartScheduled) {
    updateStatus.textContent = `当前已是最新版本 v${result.latestVersion || latestUpdateInfo.currentVersion}`;
    updateInstallButton.classList.add("hidden");
    return;
  }
  updateInstallButton.classList.add("hidden");
  updateStatus.textContent = `已下载 v${result.latestVersion}，程序即将重启完成更新`;
  showNotice("更新包已准备好，程序即将关闭并重启", true);
  window.setTimeout(() => window.close(), 1200);
}

async function openSettings() {
  settingsPanel.classList.remove("hidden");
  settingsNavButton.setAttribute("aria-expanded", "true");
  settingsStatus.textContent = "正在读取配置…";
  try {
    const [config, updateConfig, themeConfig] = await Promise.all([getAiConfig(), getUpdateConfig(), getThemeConfig()]);
    aiModelSelect.value = config.model || "deepseek-chat";
    deepseekKeyInput.value = "";
    settingsStatus.textContent = config.configured ? "API Key 已配置" : "尚未配置 API Key";
    updateAutoCheck.checked = updateConfig.autoCheck !== false;
    updateCurrentVersion.textContent = `v${updateConfig.currentVersion}`;
    const theme = applyTheme(themeConfig.theme, true);
    themeStatus.textContent = theme === "light" ? "已使用白色主题" : "已使用黑色主题";
  } catch (error) {
    settingsStatus.textContent = `读取失败：${error.message}`;
  }
}

async function saveTheme(theme) {
  const result = await postJson("/api/theme/config", { theme });
  const savedTheme = applyTheme(result.theme, true);
  themeStatus.textContent = savedTheme === "light" ? "已使用白色主题" : "已使用黑色主题";
}

function closeSettings() {
  settingsPanel.classList.add("hidden");
  settingsNavButton.setAttribute("aria-expanded", "false");
}

async function saveAiSettings() {
  try {
    const apiKey = deepseekKeyInput.value.trim();
    await postJson("/api/ai/config", {
      model: aiModelSelect.value,
      ...(apiKey ? { apiKey } : {}),
    });
    deepseekKeyInput.value = "";
    settingsStatus.textContent = "配置已保存";
  } catch (error) {
    settingsStatus.textContent = `保存失败：${error.message}`;
  }
}

async function clearAiKey() {
  try {
    await postJson("/api/ai/config", { model: aiModelSelect.value, apiKey: "" });
    deepseekKeyInput.value = "";
    settingsStatus.textContent = "API Key 已清除";
  } catch (error) {
    settingsStatus.textContent = `清除失败：${error.message}`;
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
      : "尚未配置 API Key，请先在设置中配置";
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
      if (enabled && !confirmEnableConflicts([mod])) return;
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
  const firstLoad = !catalogLoaded;
  if (firstLoad) {
    grid.innerHTML = `<div class="catalog-loading" role="status" aria-live="polite"><span class="operation-spinner" aria-hidden="true"></span><span>正在读取资源…</span></div>`;
  }
  try {
    const route = force ? `/api/catalog?refresh=${Date.now()}` : "/api/catalog";
    const response = await fetch(route, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    state.mods = payload.mods || [];
    catalogLoaded = true;
    sprayAssetsNeedRefresh = true;
    refreshModelConflictState();
    rootPath.textContent = payload.root || "当前工作目录";
    renderStats();
    render();
    return state.mods;
  } catch (error) {
    reportClientError("读取 Mod 目录", error);
    showNotice(`目录读取失败：${error.message}`);
    if (firstLoad) {
      grid.innerHTML = `<div class="empty">资源读取失败，请稍后刷新目录</div>`;
    }
  }
}

async function launchGame() {
  if (operationBusy) return;
  return runExclusiveOperation("正在启动求生之路 2，请稍候…", async () => {
    try {
      const result = await postJson("/api/game/launch", {});
      showNotice(result.mode === "direct" ? "已启动求生之路 2" : "已通过 Steam 启动求生之路 2", true);
    } catch (error) {
      showNotice(`启动游戏失败：${error.message}`);
    }
  });
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

async function findGameFolder() {
  if (operationBusy) return;
  return runExclusiveOperation("正在查找求生之路 2 的 Mod 目录，请稍候…", async () => {
    try {
      showNotice("正在查找求生之路 2 的 Mod 目录…");
      const response = await fetch("/api/find-game-folder", { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      await loadCatalog();
      const count = result.candidates?.length || 1;
      showNotice(`已切换到：${result.root}${count > 1 ? `（找到 ${count} 个游戏目录，已选择 Mod 较多的目录）` : ""}`, true);
    } catch (error) {
      showNotice(`自动查找失败：${error.message}`);
    }
  });
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
    const packageText = result.packageType === "integration"
      ? "，已识别为整合包并按游戏目录导入"
      : "";
    showNotice(`已导入 ${result.imported.length} 个文件${conflictText}${packageText}`, true);
  } catch (error) {
    showNotice(`导入失败：${error.message}`);
  }
}

function renderWorkshopSelectionState() {
  const selectedCount = workshopSelectedIds.size;
  const loading = !workshopLoading.classList.contains("hidden");
  workshopSelectedCount.textContent = `已选择 ${selectedCount} 个`;
  workshopSelectAll.checked = workshopMods.length > 0 && selectedCount === workshopMods.length;
  workshopSelectAll.indeterminate = selectedCount > 0 && selectedCount < workshopMods.length;
  workshopCopy.disabled = loading || selectedCount === 0;
}

function setWorkshopLoading(loading, message = "正在处理 Workshop Mod，请稍候…") {
  workshopLoadingMessage.textContent = message;
  workshopLoading.classList.toggle("hidden", !loading);
  workshopClose.disabled = loading;
  workshopSelectAll.disabled = loading;
  workshopList.querySelectorAll("input[data-workshop-id]").forEach((input) => {
    input.disabled = loading;
  });
  renderWorkshopSelectionState();
}

function renderWorkshopDialog() {
  workshopSummary.textContent = workshopMods.length
    ? `发现 ${workshopMods.length} 个尚未复制到工作区的 Mod`
    : "没有发现新的 Workshop Mod";
  workshopList.innerHTML = workshopMods.length
    ? workshopMods.map((mod) => {
      const preview = mod.files.find((file) => file.kind === "preview");
      const fileNames = mod.files.map((file) => file.name).join("、");
      return `<article class="workshop-item">
        <label class="workshop-select" title="选择 ${escapeHtml(mod.name)}"><input type="checkbox" data-workshop-id="${escapeHtml(mod.id)}" ${workshopSelectedIds.has(mod.id) ? "checked" : ""} /><span class="sr-only">选择 ${escapeHtml(mod.name)}</span></label>
        <div class="workshop-preview ${preview ? "" : "empty"}">${preview ? `<img src="${fileUrl(preview.path)}" alt="${escapeHtml(mod.name)} 预览图" loading="lazy" />` : `<i data-lucide="package"></i>`}</div>
        <div class="workshop-info"><h3 title="${escapeHtml(mod.name)}">${escapeHtml(mod.name)}</h3><p title="${escapeHtml(fileNames)}">${escapeHtml(fileNames)}</p><span>${mod.files.length} 个文件 · 复制到工作区根目录</span></div>
      </article>`;
    }).join("")
    : `<div class="workshop-empty">当前 Workshop 中没有待复制的 VPK。</div>`;
  renderWorkshopSelectionState();
  if (window.lucide) lucide.createIcons();
}

async function openWorkshopDialog() {
  if (operationBusy) return;
  try {
    const result = await runExclusiveOperation("正在扫描 Workshop，请稍候…", async () => {
      const response = await fetch("/api/workshop/scan", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      return payload;
    });
    if (!result) return;
    workshopMods = result.mods || [];
    workshopSelectedIds = new Set(workshopMods.map((mod) => mod.id));
    workshopStatus.textContent = result.available ? `来源：${result.path}` : "当前工作区没有 workshop 子目录";
    renderWorkshopDialog();
    if (typeof workshopDialog.showModal === "function") workshopDialog.showModal();
    else workshopDialog.setAttribute("open", "");
  } catch (error) {
    showNotice(`Workshop 扫描失败：${error.message}`);
  }
}

async function copySelectedWorkshopMods() {
  if (operationBusy) return;
  const ids = [...workshopSelectedIds];
  if (!ids.length) return;
  setWorkshopLoading(true, `正在复制 ${ids.length} 个 Workshop Mod，请稍候…`);
  try {
    const result = await runExclusiveOperation(`正在复制 ${ids.length} 个 Workshop Mod，请稍候…`, async () => {
      const response = await fetch("/api/workshop/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      await loadCatalog(true);
      return payload;
    });
    if (!result) return;
    workshopDialog.close();
    workshopMods = [];
    workshopSelectedIds = new Set();
    const details = [];
    if (result.skipped?.length) details.push(`跳过 ${result.skipped.length} 个同内容文件`);
    if (result.conflicts?.length) details.push(`冲突 ${result.conflicts.length} 个文件`);
    if (result.missing?.length) details.push(`缺少 ${result.missing.length} 个文件`);
    showNotice(`已复制 ${result.imported?.length || 0} 个文件到工作区${details.length ? `，${details.join("，")}` : ""}`, true);
  } catch (error) {
    workshopStatus.textContent = `复制失败：${error.message}`;
    workshopStatus.classList.add("error");
  } finally {
    setWorkshopLoading(false);
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
  if (button.dataset.navId === "settings") return;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  state.category = button.dataset.category;
  render();
}));
document.querySelectorAll(".role-filter").forEach((button) => button.addEventListener("click", () => {
  if (operationBusy) return;
  document.querySelectorAll(".role-filter").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  state.category = "survivor_target";
  state.roleSide = button.dataset.roleSide;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.category === "survivor_target"));
  render();
}));
document.querySelectorAll(".voice-role-filter").forEach((button) => button.addEventListener("click", () => {
  if (operationBusy) return;
  document.querySelectorAll(".voice-role-filter").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  state.category = "voice_replacement";
  state.voiceSide = button.dataset.voiceSide;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.category === "voice_replacement"));
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
settingsNavButton.addEventListener("click", () => {
  if (settingsPanel.classList.contains("hidden")) {
    openSettings();
  } else {
    closeSettings();
  }
});
sidebarToggleButton.addEventListener("click", toggleSidebar);
document.querySelector("#settings-close").addEventListener("click", closeSettings);
themeSelect.addEventListener("change", () => {
  if (operationBusy) return;
  const previous = normalizeTheme(document.documentElement.dataset.theme);
  const next = normalizeTheme(themeSelect.value);
  applyTheme(next);
  runExclusiveOperation("正在保存界面主题，请稍候…", async () => {
    try {
      await saveTheme(next);
    } catch (error) {
      applyTheme(previous);
      themeStatus.textContent = `保存失败：${error.message}`;
    }
  });
});
document.querySelector("#ai-settings-save").addEventListener("click", () => runExclusiveOperation("正在保存 AI 设置，请稍候…", saveAiSettings));
document.querySelector("#ai-settings-clear").addEventListener("click", () => runExclusiveOperation("正在清除 API Key，请稍候…", clearAiKey));
updateAutoCheck.addEventListener("change", () => {
  const enabled = updateAutoCheck.checked;
  runExclusiveOperation("正在保存更新设置，请稍候…", async () => {
    try {
      await saveUpdateCheckSetting(enabled);
    } catch (error) {
      updateAutoCheck.checked = !enabled;
      updateStatus.textContent = `保存失败：${error.message}`;
    }
  });
});
updateCheckButton.addEventListener("click", () => runExclusiveOperation("正在检查更新，请稍候…", () => checkForUpdates()));
updateInstallButton.addEventListener("click", () => runExclusiveOperation("正在下载更新，请稍候…", installUpdate));
document.querySelector("#refresh-button").addEventListener("click", refreshCatalog);
document.querySelector("#change-folder-button").addEventListener("click", changeFolder);
document.querySelector("#find-game-folder-button").addEventListener("click", findGameFolder);
document.querySelector("#reset-folder-button").addEventListener("click", resetFolder);
document.querySelector("#refresh-button-top").addEventListener("click", refreshCatalog);
launchGameButton.addEventListener("click", launchGame);
document.querySelector("#spray-manager-button").addEventListener("click", openSprayManager);
document.querySelector("#workshop-button").addEventListener("click", openWorkshopDialog);
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
document.querySelector("#workshop-close").addEventListener("click", () => workshopDialog.close());
workshopCopy.addEventListener("click", copySelectedWorkshopMods);
workshopSelectAll.addEventListener("change", () => {
  workshopSelectedIds = workshopSelectAll.checked
    ? new Set(workshopMods.map((mod) => mod.id))
    : new Set();
  workshopList.querySelectorAll("input[data-workshop-id]").forEach((input) => {
    input.checked = workshopSelectedIds.has(input.dataset.workshopId);
  });
  renderWorkshopSelectionState();
});
workshopList.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-workshop-id]");
  if (!input) return;
  if (input.checked) workshopSelectedIds.add(input.dataset.workshopId);
  else workshopSelectedIds.delete(input.dataset.workshopId);
  renderWorkshopSelectionState();
});
workshopDialog.addEventListener("click", (event) => {
  if (event.target === workshopDialog) workshopDialog.close();
});
vpkFilesList.addEventListener("click", handleVpkFileAction);
vpkFilesClose.addEventListener("click", () => vpkFilesDialog.close());
vpkFilesDialog.addEventListener("click", (event) => {
  if (event.target === vpkFilesDialog) vpkFilesDialog.close();
});
vpkFilesDialog.addEventListener("close", () => {
  delete vpkFilesDialog.dataset.modId;
});
sprayList.addEventListener("change", handleSpraySelection);
sprayList.addEventListener("click", handleSprayListClick);
sprayList.addEventListener("load", handleSprayPreviewEvent, true);
sprayList.addEventListener("error", handleSprayPreviewEvent, true);
sprayConfigBody.addEventListener("click", (event) => {
  const modeButton = event.target.closest("button[data-config-mode]");
  if (!modeButton) return;
  sprayConfigDraft = { ...sprayConfigDraft, ...collectSprayConfig(), mode: modeButton.dataset.configMode };
  if (sprayConfigDraft.mode === "dynamic" && !sprayConfigDraft.source) sprayConfigDraft.source = "images";
  renderSprayConfigEditor();
});
sprayConfigBody.addEventListener("change", (event) => {
  if (event.target.matches("input[name='spray-config-source']")) {
    sprayConfigDraft = { ...sprayConfigDraft, ...collectSprayConfig(), source: event.target.value };
    renderSprayConfigEditor();
    return;
  }
  const mipmapSelect = event.target.closest("select[data-config-mipmap]");
  if (mipmapSelect) {
    sprayConfigDraft = { ...sprayConfigDraft, ...collectSprayConfig() };
    renderSprayConfigEditor();
    return;
  }
  const frameInput = event.target.closest("input[data-config-frame-asset]");
  if (frameInput) {
    const duration = sprayConfigBody.querySelector(`[data-config-duration='${CSS.escape(frameInput.dataset.configFrameAsset)}']`);
    if (duration) duration.disabled = !frameInput.checked;
  }
  renderSprayConfigPreview();
});
sprayConfigBody.addEventListener("input", () => renderSprayConfigPreview());
spraySlotUsage.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-spray-slot]");
  if (button) focusSprayAsset(button.dataset.spraySlot);
});
sprayTabs.forEach((tab) => tab.addEventListener("click", () => setSpraySourceTab(tab.dataset.spraySource)));
sprayImportButton.addEventListener("click", () => sprayImportInput.click());
sprayImportInput.addEventListener("change", (event) => {
  importSprayImages(event.target.files).catch((error) => showNotice(`导入图片失败：${error.message}`));
  event.target.value = "";
});
sprayDialog.addEventListener("dragenter", (event) => {
  if (!hasDraggedFiles(event) || operationBusy) return;
  event.preventDefault();
  sprayDragDepth += 1;
  setSprayDropActive(true);
});
sprayDialog.addEventListener("dragover", (event) => {
  if (!hasDraggedFiles(event) || operationBusy) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
  setSprayDropActive(true);
});
sprayDialog.addEventListener("dragleave", (event) => {
  if (!hasDraggedFiles(event)) return;
  sprayDragDepth = Math.max(0, sprayDragDepth - 1);
  if (!sprayDialog.contains(event.relatedTarget)) {
    sprayDragDepth = 0;
    setSprayDropActive(false);
  }
});
sprayDialog.addEventListener("drop", (event) => {
  if (!hasDraggedFiles(event) || operationBusy) return;
  event.preventDefault();
  sprayDragDepth = 0;
  setSprayDropActive(false);
  importSprayImages(event.dataTransfer.files).catch((error) => showNotice(`导入图片失败：${error.message}`));
});
sprayApply.addEventListener("click", applySprayCollection);
sprayReset.addEventListener("click", resetSprayUsage);
sprayClose.addEventListener("click", () => sprayDialog.close());
sprayDialog.addEventListener("click", (event) => {
  if (event.target === sprayDialog && !operationBusy) sprayDialog.close();
});
sprayDialog.addEventListener("close", () => {
  sprayDragDepth = 0;
  setSprayDropActive(false);
  setSprayLoading(false);
});
sprayConfigSave.addEventListener("click", () => saveSprayConfig().catch((error) => {
  sprayConfigStatus.textContent = `保存失败：${error.message}`;
  sprayConfigStatus.classList.add("error");
}));
sprayConfigCancel.addEventListener("click", () => sprayConfigDialog.close());
sprayConfigClose.addEventListener("click", () => sprayConfigDialog.close());
sprayConfigDialog.addEventListener("click", (event) => {
  if (event.target === sprayConfigDialog && !operationBusy) sprayConfigDialog.close();
});
sprayConfigDialog.addEventListener("close", () => {
  stopSprayConfigPreview();
  sprayConfigAsset = null;
  sprayConfigDraft = null;
  sprayConfigStatus.textContent = "";
  sprayConfigStatus.classList.remove("error");
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

restoreSidebarState();
const initialNavOrder = restoreNavOrder();
restoreNavOrderFromServer(initialNavOrder);
initializeNavDragging();
if (window.lucide) lucide.createIcons();
initializeTheme();
loadCatalog();
getUpdateConfig().then((config) => {
  if (config.autoCheck) checkForUpdates({ automatic: true });
}).catch(() => {
  // Update checks must never prevent the Mod library from opening.
});
checkForSourceChanges();
window.setInterval(checkForSourceChanges, 1000);

window.addEventListener("error", (event) => {
  reportClientError(`前端脚本 ${event.filename || "未知文件"}:${event.lineno || 0}`, event.error || event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  reportClientError("前端异步任务", event.reason);
});
