"""Sorting logic for To-do Sort."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .const import ORDER_DESC

_NUM_SPLIT = re.compile(r"(\d+)")


def natural_key(text: str | None) -> tuple[Any, ...]:
    """Case-insensitive natural sort key, so "Item 2" sorts before "Item 10"."""
    parts = _NUM_SPLIT.split((text or "").strip().casefold())
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts if p)


def target_order(items: list[Any], order: str) -> list[str]:
    """Return item uids in the requested order. Stable for equal names."""
    keyed = [
        (natural_key(item.summary), idx, item.uid)
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
                f"{entity.entity_id} does not support reordering items"
            ) from err
    return len(moves)
