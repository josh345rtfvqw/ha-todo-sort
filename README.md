# To-do Sort for Home Assistant

Adds alphabetical sorting to Home Assistant to-do lists, right inside the built-in To-do page.

Open any list, tap the three-dot menu, and you get:

- **Sort A to Z** and **Sort Z to A**: sorts the list once. You can still drag items around afterwards.
- **Keep sorted A to Z**: the list re-sorts itself whenever an item is added or renamed, from any device, voice or automation. Turn it off to go back to drag-to-reorder.

Sorting ignores case and handles numbers properly ("item 2" before "item 10"). The built-in `shopping_list.sort` puts "Zucchini" before "apples"; this doesn't.

Works with any to-do list that supports reordering, including the built-in Shopping list and Local To-do lists. Lists that can't be reordered (some cloud services) don't show the options.

## Install

### HACS
1. HACS > three dots > Custom repositories > add this repo's URL, type **Integration**.
2. Download **To-do Sort**, then restart Home Assistant.
3. Settings > Devices & services > Add integration > **To-do Sort**.
4. Hard refresh the browser (or clear the app cache in the Companion app).

### Manual
1. Copy `custom_components/todo_sort` into your `config/custom_components/` folder.
2. Restart Home Assistant, then do steps 3 and 4 above.

## Actions

Both also work in automations and scripts.

```yaml
# Sort once
action: todo_sort.sort
target:
  entity_id: todo.shopping_list
data:
  order: alpha_asc   # or alpha_desc

# Keep a list sorted (or set mode: "off" to stop)
action: todo_sort.set_auto_sort
target:
  entity_id: todo.shopping_list
data:
  mode: alpha_asc   # off, alpha_asc, alpha_desc
```

## How it works

The sort changes the list's stored order, so every view (To-do page, cards, phone app) shows the same thing. It moves as few items as it can: adding one item to a sorted list is a single move.

The menu items come from a small script the integration loads into the frontend. It hooks into the To-do page's existing menu. If a future Home Assistant release changes that menu, the actions above keep working and the menu items are the only thing that might need an update.

Tested on Home Assistant 2026.10.
