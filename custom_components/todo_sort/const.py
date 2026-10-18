"""Constants for To-do Sort."""

DOMAIN = "todo_sort"
VERSION = "1.1.0"

SERVICE_SORT = "sort"
SERVICE_SET_AUTO_SORT = "set_auto_sort"
SERVICE_REMOVE_DUPLICATES = "remove_duplicates"

ATTR_ORDER = "order"
ATTR_MODE = "mode"

ORDER_ASC = "alpha_asc"
ORDER_DESC = "alpha_desc"
ORDERS = (ORDER_ASC, ORDER_DESC)

MODE_OFF = "off"
MODES = (MODE_OFF, ORDER_ASC, ORDER_DESC)

STORAGE_KEY = f"{DOMAIN}.settings"
STORAGE_VERSION = 1

FRONTEND_URL = f"/{DOMAIN}/todo-sort.js"

# Wait this long after the last change before auto-sorting, so a burst of
# edits (or our own moves) only triggers one sort.
AUTO_SORT_DELAY = 0.75
