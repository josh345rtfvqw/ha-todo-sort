"""Tests for the sorting and duplicate logic. No running Home Assistant needed."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

import pytest
from homeassistant.components.todo import TodoItemStatus

from custom_components.todo_sort.const import ORDER_ASC, ORDER_DESC
from custom_components.todo_sort.sorter import (
    async_dedupe_entity,
    async_sort_entity,
    is_sorted,
    plan_dedupe,
    plan_moves,
    strip_quantity,
    target_order,
)

DONE = TodoItemStatus.COMPLETED
TODO = TodoItemStatus.NEEDS_ACTION


@dataclass
class Item:
    summary: str
    uid: str = ""
    status: TodoItemStatus = TODO
    description: str | None = None
    due: date | None = None


def items(*names: str) -> list[Item]:
    return [Item(name, uid=f"u{i}") for i, name in enumerate(names)]


def names_in(order: list[str], source: list[Item]) -> list[str]:
    by_uid = {i.uid: i.summary for i in source}
    return [by_uid[u] for u in order]


class FakeList:
    """Applies moves and deletes the way a to-do entity would."""

    entity_id = "todo.test"

    def __init__(self, todo_items: list[Item]) -> None:
        self.todo_items = todo_items
        self.moves = 0

    async def async_move_todo_item(self, uid: str, previous_uid: str | None) -> None:
        self.moves += 1
        item = next(i for i in self.todo_items if i.uid == uid)
        self.todo_items.remove(item)
        pos = 0
        if previous_uid:
            pos = next(n for n, i in enumerate(self.todo_items) if i.uid == previous_uid) + 1
        self.todo_items.insert(pos, item)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self.todo_items = [i for i in self.todo_items if i.uid not in uids]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 eggs", "eggs"),
        ("3x milk", "milk"),
        ("3 x milk", "milk"),
        ("1.5 kg rice", "rice"),
        ("500g flour", "flour"),
        ("1/2 lb butter", "butter"),
        ("12 Bread rolls", "Bread rolls"),
        ("7up", "7up"),
        ("4th of July", "4th of July"),
        ("2 xbox games", "xbox games"),
        ("2 lemons", "lemons"),
        ("42", "42"),
        ("Item 2", "Item 2"),
        ("", ""),
    ],
)
def test_strip_quantity(text: str, expected: str) -> None:
    assert strip_quantity(text) == expected


def test_sort_ignores_case_and_numbers_sort_naturally() -> None:
    src = items("item 10", "Zucchini", "apples", "Item 2", "banana")
    assert names_in(target_order(src, ORDER_ASC), src) == [
        "apples",
        "banana",
        "Item 2",
        "item 10",
        "Zucchini",
    ]


def test_sort_ignores_leading_quantity() -> None:
    src = items("2 eggs", "apples", "3x milk", "500g flour", "bread")
    assert names_in(target_order(src, ORDER_ASC), src) == [
        "apples",
        "bread",
        "2 eggs",
        "500g flour",
        "3x milk",
    ]


def test_same_name_different_quantity_sorts_by_quantity() -> None:
    src = items("10 eggs", "eggs", "2 eggs")
    assert names_in(target_order(src, ORDER_ASC), src) == ["2 eggs", "10 eggs", "eggs"]


def test_descending() -> None:
    src = items("b", "C", "a")
    assert names_in(target_order(src, ORDER_DESC), src) == ["C", "b", "a"]


def test_equal_names_keep_their_order_both_ways() -> None:
    src = items("Milk", "milk", "apple")
    assert names_in(target_order(src, ORDER_ASC), src) == ["apple", "Milk", "milk"]
    assert target_order(src, ORDER_DESC) == ["u0", "u1", "u2"]


def test_items_without_uid_are_skipped() -> None:
    src = [Item("b", uid="u1"), Item("a")]
    assert target_order(src, ORDER_ASC) == ["u1"]


def test_plan_moves_already_sorted() -> None:
    assert plan_moves(["a", "b"], ["a", "b"]) == []


def test_plan_moves_one_new_item_is_one_move() -> None:
    assert plan_moves(["a", "c", "d", "b"], ["a", "b", "c", "d"]) == [("b", "a")]


def test_plan_moves_new_first_item_goes_to_top() -> None:
    assert plan_moves(["b", "c", "a"], ["a", "b", "c"]) == [("a", None)]


@pytest.mark.parametrize("seed", range(25))
async def test_sort_entity_reaches_target(seed: int) -> None:
    rng = random.Random(seed)
    words = ["apple", "Banana", "2 eggs", "milk", "item 10", "Item 2", "zucchini", "bread"]
    src = [Item(rng.choice(words), uid=f"u{i}") for i in range(rng.randint(0, 12))]
    rng.shuffle(src)
    order = rng.choice([ORDER_ASC, ORDER_DESC])
    fake = FakeList(list(src))
    moves = await async_sort_entity(fake, order)
    assert is_sorted(fake.todo_items, order)
    assert moves == fake.moves <= len(src)


async def test_sort_entity_sorted_list_makes_no_moves() -> None:
    fake = FakeList(items("a", "b", "c"))
    assert await async_sort_entity(fake, ORDER_ASC) == 0


def test_dedupe_ignores_case_and_spaces() -> None:
    src = items("Milk", "milk ", "bread", "MILK", "  bread")
    assert plan_dedupe(src) == ["u1", "u3", "u4"]


def test_dedupe_different_quantities_are_not_duplicates() -> None:
    assert plan_dedupe(items("eggs", "2 eggs", "10 eggs")) == []


def test_dedupe_keeps_the_to_do_copy_over_completed() -> None:
    src = [Item("milk", "u0", DONE), Item("Milk", "u1", TODO)]
    assert plan_dedupe(src) == ["u0"]


def test_dedupe_completed_only_keeps_first() -> None:
    src = [Item("milk", "u0", DONE), Item("milk", "u1", DONE)]
    assert plan_dedupe(src) == ["u1"]


def test_dedupe_keeps_copies_with_their_own_details() -> None:
    src = [
        Item("milk", "u0"),
        Item("milk", "u1", description="oat"),
        Item("milk", "u2", due=date(2026, 10, 20)),
        Item("milk", "u3"),
    ]
    assert plan_dedupe(src) == ["u3"]


def test_dedupe_matching_details_are_still_duplicates() -> None:
    src = [Item("milk", "u0", description="oat"), Item("milk", "u1", description="oat")]
    assert plan_dedupe(src) == ["u1"]


def test_dedupe_skips_blank_and_uid_less_items() -> None:
    src = [Item("", "u0"), Item("", "u1"), Item("milk"), Item("milk", "u3")]
    assert plan_dedupe(src) == []


async def test_dedupe_entity_deletes() -> None:
    fake = FakeList(items("milk", "bread", "Milk"))
    assert await async_dedupe_entity(fake) == 1
    assert [i.summary for i in fake.todo_items] == ["milk", "bread"]


async def test_dedupe_entity_nothing_to_do() -> None:
    fake = FakeList(items("milk", "bread"))
    assert await async_dedupe_entity(fake) == 0
