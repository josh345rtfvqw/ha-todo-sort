"""Sorting logic for To-do Sort."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.todo import TodoItemStatus
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, ORDER_DESC

_NUM_SPLIT = re.compile(r"(\d+)")
# A leading quantity such as "2 ", "3x ", "1.5 kg " or "1/2 lb ". It only
# counts when a name follows, so "7up" and "4th of July" are left alone.
_QUANTITY = re.compile(
    r"^\d+(?:[.,/]\d+)?\s*(?:x|×|g|kg|mg|ml|cl|l|lb|lbs|oz|pk|pack|packs)?\.?\s+(?=\S)",
    re.IGNORECASE,
)


def natural_key(text: str | None) -> tuple[Any, ...]:
    """Case-insensitive natural sort key, so "Item 2" sorts before "Item 10"."""
    parts = _NUM_SPLIT.split((text or "").strip().casefold())
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts if p)


def strip_quantity(text: str | None) -> str:
    """Drop a leading quantity, so "2 eggs" sorts as "eggs"."""
    text = (text or "").strip()
    return _QUANTITY.sub("", text, count=1)


def item_key(text: str | None) -> tuple[Any, ...]:
    """Sort key for an item name: by name ignoring quantity, then by quantity."""
    return (natural_key(strip_quantity(text)), natural_key(text))


def target_order(items: list[Any], order: str) -> list[str]:
    """Return item uids in the requested order. Stable for equal names."""
    keyed = [
        (item_key(item.summary), idx, item.uid)
        for idx, item in enumerate(items)
        if item.uid
    ]
    keyed.sort(key=lambda k: (k[0], k[1]))
    uids = [uid for _, _, uid in keyed]
    if order == ORDER_DESC:
        # Reverse by name but keep equal names in their original relative order.
        keyed.sort(key=lambda k: (k[0], -k[1]), reverse=True)
        uids = [uid for _, _, uid in keyed]
    return uids


def _longest_increasing(positions: list[int]) -> set[int]:
    """Indexes (into positions) of one longest strictly increasing subsequence."""
    tails: list[int] = []  # index into positions of the smallest tail per length
    prev: list[int] = [-1] * len(positions)
    for i, pos in enumerate(positions):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if positions[tails[mid]] < pos:
                lo = mid + 1
            else:
                hi = mid
        if lo > 0:
            prev[i] = tails[lo - 1]
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    keep: set[int] = set()
    i = tails[-1] if tails else -1
    while i != -1:
        keep.add(i)
        i = prev[i]
    return keep


def plan_moves(current: list[str], target: list[str]) -> list[tuple[str, str | None]]:
    """Work out the fewest (uid, previous_uid) moves to turn current into target.

    Items on the longest run that is already in the right relative order stay
    put. Everything else is moved, in target order, to sit directly after the
    item that should precede it. Adding one item to an already sorted list
    costs a single move.
    """
    if current == target:
        return []
    index = {uid: i for i, uid in enumerate(target)}
    current = [uid for uid in current if uid in index]
    keep = {current[i] for i in _longest_increasing([index[u] for u in current])}
    moves: list[tuple[str, str | None]] = []
    for i, uid in enumerate(target):
        if uid in keep:
            continue
        moves.append((uid, target[i - 1] if i else None))
    return moves


def is_sorted(items: list[Any], order: str) -> bool:
    """True if the list is already in the requested order."""
    return [i.uid for i in items if i.uid] == target_order(items, order)


async def async_sort_entity(entity: Any, order: str) -> int:
    """Sort one to-do entity in place. Returns the number of moves made."""
    items = list(entity.todo_items or [])
    current = [i.uid for i in items if i.uid]
    moves = plan_moves(current, target_order(items, order))
    for uid, previous_uid in moves:
        try:
            await entity.async_move_todo_item(uid=uid, previous_uid=previous_uid)
        except NotImplementedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_reorder",
                translation_placeholders={"entity_id": entity.entity_id},
            ) from err
    return len(moves)


def _dedupe_name(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def plan_dedupe(items: list[Any]) -> list[str]:
    """Return uids of items that repeat an earlier item's name.

    Names match ignoring case and extra spaces, but not quantity ("2 eggs" and
    "eggs" are different items). The copy that's still to do wins over a
    completed one, otherwise the first in the list wins. A copy with its own
    description or due date is kept, so nothing typed into it is lost.
    """
    ranked = sorted(
        enumerate(items),
        key=lambda p: (p[1].status == TodoItemStatus.COMPLETED, p[0]),
    )
    kept: dict[str, Any] = {}
    remove: list[str] = []
    for _, item in ranked:
        name = _dedupe_name(item.summary)
        if not item.uid or not name:
            continue
        keep = kept.get(name)
        if keep is None:
            kept[name] = item
            continue
        details = (item.description or "", item.due)
        if details not in (("", None), (keep.description or "", keep.due)):
            continue
        remove.append(item.uid)
    return remove


async def async_dedupe_entity(entity: Any) -> int:
    """Delete repeated items from one to-do entity. Returns how many went."""
    uids = plan_dedupe(list(entity.todo_items or []))
    if uids:
        await entity.async_delete_todo_items(uids)
    return len(uids)
