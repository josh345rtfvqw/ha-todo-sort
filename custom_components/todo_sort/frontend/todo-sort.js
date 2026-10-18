// To-do Sort: adds sort options to the three-dot menu on the built-in To-do page.
// Loaded on every frontend page by the todo_sort integration.

(() => {
  if (window.__todoSortLoaded) return;
  window.__todoSortLoaded = true;

  const DELETE_TODO_ITEM = 2;
  const MOVE_TODO_ITEM = 8;
  const MARK = "data-todo-sort";
  const ICON_ASC =
    "M19 17H22L18 21L14 17H17V3H19M11 13V15L7.67 19H11V21H5V19L8.33 15H5V13M9 3H7C5.9 3 5 3.9 5 5V11H7V9H9V11H11V5C11 3.9 10.11 3 9 3M9 7H7V5H9Z";
  const ICON_DESC =
    "M19 7H22L18 3L14 7H17V21H19M11 13V15L7.67 19H11V21H5V19L8.33 15H5V13M9 3H7C5.9 3 5 3.9 5 5V11H7V9H9V11H11V5C11 3.9 10.11 3 9 3M9 7H7V5H9Z";
  const ICON_DEDUPE =
    "M14 10H3V12H14V10M14 6H3V8H14V6M3 16H10V14H3V16M14.4 22L17 19.4L19.6 22L21 20.6L18.4 18L21 15.4L19.6 14L17 16.6L14.4 14L13 15.4L15.6 18L13 20.6L14.4 22Z";

  // Menu labels and messages. To add a language, copy "en" and translate it.
  // Keys are Home Assistant language codes ("de", "pt-BR"); a regional code
  // falls back to its base language, then to English.
  const STRINGS = {
    en: {
      sort_asc: "Sort A to Z",
      sort_desc: "Sort Z to A",
      keep_sorted: "Keep sorted A to Z",
      remove_duplicates: "Remove duplicates",
      sorted_asc: "Sorted A to Z",
      sorted_desc: "Sorted Z to A",
      sort_failed: "Couldn't sort: {error}",
      auto_on: "This list now stays sorted A to Z",
      auto_off: "Auto-sort off. Drag to reorder.",
      auto_failed: "Couldn't change auto-sort: {error}",
      removed_none: "No duplicates found",
      removed_one: "Removed 1 duplicate",
      removed_many: "Removed {count} duplicates",
      removed_unknown: "Duplicates removed",
      remove_failed: "Couldn't remove duplicates: {error}",
    },
  };

  let autoSort = {};
  let settingsLoaded = false;
  let settingsLoading = null;
  const wired = new WeakSet();

  const t = (panel, key, vars = {}) => {
    const hass = panel.hass || {};
    const lang = (hass.locale && hass.locale.language) || hass.language || "en";
    const table = STRINGS[lang] || STRINGS[lang.split("-")[0]] || STRINGS.en;
    const text = table[key] || STRINGS.en[key] || key;
    return text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? vars[name] : m));
  };

  const errorText = (err) => (err && err.message) || String(err);

  const toast = (el, message) =>
    el.dispatchEvent(
      new CustomEvent("hass-notification", {
        detail: { message },
        bubbles: true,
        composed: true,
      })
    );

  const loadSettings = (panel) => {
    if (settingsLoading) return settingsLoading;
    settingsLoading = panel.hass
      .callWS({ type: "todo_sort/settings" })
      .then((res) => {
        autoSort = (res && res.auto_sort) || {};
        settingsLoaded = true;
      })
      .catch(() => {})
      .finally(() => {
        settingsLoading = null;
        panel.requestUpdate && panel.requestUpdate();
      });
    return settingsLoading;
  };

  const supports = (panel, feature) => {
    const id = panel._entityId;
    const st = id && panel.hass && panel.hass.states[id];
    return !!st && ((st.attributes.supported_features || 0) & feature) !== 0;
  };
  const canSort = (panel) => supports(panel, MOVE_TODO_ITEM);
  const canDelete = (panel) => supports(panel, DELETE_TODO_ITEM);

  const sortNow = async (panel, order) => {
    const id = panel._entityId;
    try {
      await panel.hass.callService("todo_sort", "sort", { order }, { entity_id: id });
      toast(panel, t(panel, order === "alpha_desc" ? "sorted_desc" : "sorted_asc"));
    } catch (err) {
      toast(panel, t(panel, "sort_failed", { error: errorText(err) }));
    }
  };

  const removeDuplicates = async (panel) => {
    const id = panel._entityId;
    try {
      const res = await panel.hass.callService(
        "todo_sort",
        "remove_duplicates",
        {},
        { entity_id: id },
        true,
        true
      );
      const count = res && res.response ? res.response.removed : undefined;
      let key = "removed_unknown";
      if (count === 0) key = "removed_none";
      else if (count === 1) key = "removed_one";
      else if (typeof count === "number") key = "removed_many";
      toast(panel, t(panel, key, { count }));
    } catch (err) {
      toast(panel, t(panel, "remove_failed", { error: errorText(err) }));
    }
  };

  const toggleAuto = async (panel) => {
    const id = panel._entityId;
    const mode = autoSort[id] ? "off" : "alpha_asc";
    try {
      await panel.hass.callService("todo_sort", "set_auto_sort", { mode }, { entity_id: id });
      if (mode === "off") delete autoSort[id];
      else autoSort[id] = mode;
      toast(panel, t(panel, mode === "off" ? "auto_off" : "auto_on"));
    } catch (err) {
      toast(panel, t(panel, "auto_failed", { error: errorText(err) }));
    }
    loadSettings(panel);
  };

  const makeItem = (value, label, icon, checkbox) => {
    const item = document.createElement("ha-dropdown-item");
    item.setAttribute(MARK, "");
    item.value = value;
    item.setAttribute("value", value);
    if (checkbox) {
      item.type = "checkbox";
      item.setAttribute("type", "checkbox");
    } else {
      const svg = document.createElement("ha-svg-icon");
      svg.slot = "icon";
      svg.path = icon;
      item.append(svg);
    }
    const text = document.createElement("span");
    text.setAttribute("data-label", label);
    item.append(text);
    return item;
  };

  const injectDropdown = (panel, dropdown) => {
    let items = dropdown.querySelectorAll(`[${MARK}]`);
    if (items.length === 0) {
      const divider = document.createElement("wa-divider");
      divider.setAttribute(MARK, "");
      const nodes = [
        divider,
        makeItem("todo_sort_asc", "sort_asc", ICON_ASC),
        makeItem("todo_sort_desc", "sort_desc", ICON_DESC),
        makeItem("todo_sort_auto", "keep_sorted", null, true),
        makeItem("todo_sort_dedupe", "remove_duplicates", ICON_DEDUPE),
      ];
      // Insert after "Assist" so Lit's conditional "Delete list" part, which
      // sits at the end, can't wipe our items when it re-renders.
      const anchor = dropdown.querySelector('ha-dropdown-item[value="assist"]');
      if (anchor) anchor.after(...nodes);
      else dropdown.append(...nodes);
      items = dropdown.querySelectorAll(`[${MARK}]`);
    }

    if (!wired.has(dropdown)) {
      wired.add(dropdown);
      dropdown.addEventListener("wa-select", (ev) => {
        const value = ev.detail && ev.detail.item && ev.detail.item.value;
        if (value === "todo_sort_asc") sortNow(panel, "alpha_asc");
        else if (value === "todo_sort_desc") sortNow(panel, "alpha_desc");
        else if (value === "todo_sort_auto") toggleAuto(panel);
        else if (value === "todo_sort_dedupe") removeDuplicates(panel);
      });
    }

    const sortable = canSort(panel);
    const deletable = canDelete(panel);
    const auto = !!autoSort[panel._entityId];
    items.forEach((el) => {
      const label = el.querySelector("[data-label]");
      if (label) {
        const text = t(panel, label.getAttribute("data-label"));
        if (label.textContent !== text) label.textContent = text;
      }
      if (el.value === "todo_sort_dedupe") el.hidden = !deletable;
      else if (el.tagName === "WA-DIVIDER") el.hidden = !sortable && !deletable;
      else el.hidden = !sortable;
      if (el.value === "todo_sort_auto" && el.checked !== auto) el.checked = auto;
      if (el.value === "todo_sort_desc") el.disabled = auto;
      if (el.value === "todo_sort_asc") el.disabled = auto;
    });
  };

  // Older frontends without ha-dropdown: add a single "Sort A to Z" button.
  const injectFallback = (panel, root) => {
    const menu = root.querySelector('[slot="actionItems"]');
    if (!menu || root.querySelector(`ha-icon-button[${MARK}]`)) return;
    const btn = document.createElement("ha-icon-button");
    btn.setAttribute(MARK, "");
    btn.slot = "actionItems";
    btn.label = t(panel, "sort_asc");
    btn.path = ICON_ASC;
    btn.addEventListener("click", () => sortNow(panel, "alpha_asc"));
    menu.before(btn);
  };

  const inject = (panel) => {
    const root = panel.shadowRoot;
    if (!root || !panel.hass) return;
    if (!settingsLoaded) loadSettings(panel);
    const dropdown = root.querySelector('ha-dropdown[slot="actionItems"]');
    if (dropdown) injectDropdown(panel, dropdown);
    else if (canSort(panel)) injectFallback(panel, root);
  };

  customElements.whenDefined("ha-panel-todo").then(() => {
    const Panel = customElements.get("ha-panel-todo");
    const proto = Panel.prototype;
    if (proto.__todoSortPatched) return;
    proto.__todoSortPatched = true;
    const original = proto.updated;
    proto.updated = function (changed) {
      if (original) original.call(this, changed);
      try {
        inject(this);
      } catch (err) {
        console.warn("todo_sort: could not add menu items", err);
      }
    };
  });
})();
