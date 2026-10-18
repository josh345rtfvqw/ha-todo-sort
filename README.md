# To-do Sort for Home Assistant

Adds alphabetical sorting to Home Assistant to-do lists, right inside the built-in To-do page.

Open any list, tap the three-dot menu, and you get:

- **Sort A to Z** and **Sort Z to A**: sorts the list once. You can still drag items around afterwards.
- **Keep sorted A to Z**: the list re-sorts itself whenever an item is added or renamed, from any device, voice or automation. Turn it off to go back to drag-to-reorder.
- **Remove duplicates**: deletes items that repeat another item's name, ignoring case. If one copy is still to do and another is completed, the to-do copy stays. A copy with its own description or due date is never removed.

Sorting ignores case, handles numbers properly ("item 2" before "item 10") and skips a leading quantity, so "2 eggs", "3x milk" and "500g flour" sort under E, M and F. The built-in `shopping_list.sort` puts "Zucchini" before "apples"; this doesn't.

Works with any to-do list that supports reordering, including the built-in Shopping list and Local To-do lists. Lists that can't be reordered (some cloud services) don't show the sort options, and lists that don't allow deleting don't show Remove duplicates.

If you rename a list, it stays kept sorted. If you delete one, its setting is cleaned up.

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

All of these also work in automations and scripts.

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

# Remove duplicates. Add response_variable to get back how many were removed.
action: todo_sort.remove_duplicates
target:
  entity_id: todo.shopping_list
response_variable: result   # result.removed
```

## How it works

The sort changes the list's stored order, so every view (To-do page, cards, phone app) shows the same thing. It moves as few items as it can: adding one item to a sorted list is a single move.

The menu items come from a small script the integration loads into the frontend. It hooks into the To-do page's existing menu. If a future Home Assistant release changes that menu, the actions above keep working and the menu items are the only thing that might need an update.

## Translations

Action names, descriptions and error messages are in `custom_components/todo_sort/translations/`. Add a file such as `de.json` copied from `en.json`. The menu labels and pop-up messages are in the `STRINGS` table at the top of `custom_components/todo_sort/frontend/todo-sort.js`.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

Tested on Home Assistant 2026.10.
