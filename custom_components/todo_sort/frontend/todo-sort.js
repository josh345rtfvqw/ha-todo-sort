// To-do Sort: adds sort options to the three-dot menu on the built-in To-do page.
// Loaded on every frontend page by the todo_sort integration.

(() => {
  if (window.__todoSortLoaded) return;
  window.__todoSortLoaded = true;

  const MOVE_TODO_ITEM = 8;
  const MARK = "data-todo-sort";
  const ICON_ASC =
    "M19 17H22L18 21L14 17H17V3H19M11 13V15L7.67 19H11V21H5V19L8.33 15H5V13M9 3H7C5.9 3 5 3.9 5 5V11H7V9H9V11H11V5C11 3.9 10.11 3 9 3M9 7H7V5H9Z";
  const ICON_DESC =
    "M19 7H22L18 3L14 7H17V21H19M11 13V15L7.67 19H11V21H5V19L8.33 15H5V13M9 3H7C5.9 3 5 3.9 5 5V11H7V9H9V11H11V5C11 3.9 10.11 3 9 3M9 7H7V5H9Z";

  let autoSort = {};
  let settingsLoaded = false;
  let settingsLoading = null;
  const wired = new WeakSet();

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

  const canSort = (panel) => {
    const id = panel._entityId;
    const st = id && panel.hass && panel.hass.states[id];
    return !!st && ((st.attributes.supported_features || 0) & MOVE_TODO_ITEM) !== 0;
  };

  const sortNow = async (panel, order) => {
    const id = panel._entityId;
    try {
      await panel.hass.callService("todo_sort", "sort", { order }, { entity_id: id });
      toast(panel, order === "alpha_desc" ? "Sorted Z to A" : "Sorted A to Z");
    } catch (err) {
      toast(panel, `Couldn't sort: ${(err && err.message) || err}`);
    }
  };

  const toggleAuto = async (panel) => {
    const id = panel._entityId;
    const mode = autoSort[id] ? "off" : "alpha_asc";
    try {
      await panel.hass.callService("todo_sort", "set_auto_sort", { mode }, { entity_id: id });
      if (mode === "off") delete autoSort[id];
      else autoSort[id] = mode;
      toast(panel, mode === "off" ? "Auto-sort off. Drag to reorder." : "This list now stays sorted A to Z");
    } catch (err) {
      toast(panel, `Couldn't change auto-sort: ${(err && err.message) || err}`);
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
    item.append(document.createTextNode(label));
    return item;
  };

  const injectDropdown = (panel, dropdown) => {
    let items = dropdown.querySelectorAll(`[${MARK}]`);
    if (items.length === 0) {
      const divider = document.createElement("wa-divider");
      divider.setAttribute(MARK, "");
      const nodes = [
        divider,
        makeItem("todo_sort_asc", "Sort A to Z", ICON_ASC),
        makeItem("todo_sort_desc", "Sort Z to A", ICON_DESC),
        makeItem("todo_sort_auto", "Keep sorted A to Z", null, true),
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
      });
    }

    const show = canSort(panel);
    const auto = !!autoSort[panel._entityId];
    items.forEach((el) => {
      el.hidden = !show;
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
    btn.label = "Sort A to Z";
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
