"""To-do Sort: alphabetical sorting and auto-sort for Home Assistant to-do lists."""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.todo import TodoListEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er, service as service_helper
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_MODE,
    ATTR_ORDER,
    AUTO_SORT_DELAY,
    DOMAIN,
    FRONTEND_URL,
    MODE_OFF,
    MODES,
    ORDER_ASC,
    ORDERS,
    SERVICE_REMOVE_DUPLICATES,
    SERVICE_SET_AUTO_SORT,
    SERVICE_SORT,
    STORAGE_KEY,
    STORAGE_VERSION,
    VERSION,
)
from .sorter import async_dedupe_entity, async_sort_entity, is_sorted

_LOGGER = logging.getLogger(__name__)


def _todo_component(hass: HomeAssistant) -> Any:
    return hass.data.get("todo")


def _get_entity(hass: HomeAssistant, entity_id: str) -> Any:
    component = _todo_component(hass)
    return component.get_entity(entity_id) if component else None


def _supports(entity: Any, feature: TodoListEntityFeature) -> bool:
    return bool((entity.supported_features or 0) & feature)


def _supports_move(entity: Any) -> bool:
    return _supports(entity, TodoListEntityFeature.MOVE_TODO_ITEM)


def _error(key: str, entity_id: str | None = None) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={"entity_id": entity_id} if entity_id else None,
    )


async def _extract_entity_ids(hass: HomeAssistant, call: ServiceCall) -> set[str]:
    """Resolve entity_id/area/device targets. Signature changed in 2025.x."""
    params = inspect.signature(service_helper.async_extract_entity_ids).parameters
    if "hass" in params:
        result = service_helper.async_extract_entity_ids(hass, call)
    else:
        result = service_helper.async_extract_entity_ids(call)
    if inspect.isawaitable(result):
        result = await result
    entity_ids = {e for e in result if e.startswith("todo.")}
    if not entity_ids:
        raise _error("no_target")
    return entity_ids


class TodoSortManager:
    """Holds auto-sort settings and keeps the chosen lists sorted."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.auto_sort: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._subs: dict[str, tuple[Any, CALLBACK_TYPE]] = {}
        self._timers: dict[str, CALLBACK_TYPE] = {}
        self._unsubs: list[CALLBACK_TYPE] = []

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.auto_sort = {
            k: v for k, v in (data.get("auto_sort") or {}).items() if v in ORDERS
        }
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_registry_updated
            )
        )
        self._unsubs.append(async_at_started(self.hass, self._prune_missing))
        for entity_id in self.auto_sort:
            self._ensure_subscribed(entity_id)

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for _, unsub in self._subs.values():
            unsub()
        self._subs.clear()
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    def _lock(self, entity_id: str) -> asyncio.Lock:
        return self._locks.setdefault(entity_id, asyncio.Lock())

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"auto_sort": dict(self.auto_sort)}, 1)

    async def async_sort(self, entity_id: str, order: str) -> int:
        entity = _get_entity(self.hass, entity_id)
        if entity is None:
            raise _error("not_found", entity_id)
        if not _supports_move(entity):
            raise _error("cannot_reorder", entity_id)
        async with self._lock(entity_id):
            moves = await async_sort_entity(entity, order)
        _LOGGER.debug("Sorted %s (%s) with %s moves", entity_id, order, moves)
        return moves

    async def async_remove_duplicates(self, entity_id: str) -> int:
        entity = _get_entity(self.hass, entity_id)
        if entity is None:
            raise _error("not_found", entity_id)
        if not _supports(entity, TodoListEntityFeature.DELETE_TODO_ITEM):
            raise _error("cannot_delete", entity_id)
        async with self._lock(entity_id):
            removed = await async_dedupe_entity(entity)
        _LOGGER.debug("Removed %s duplicates from %s", removed, entity_id)
        return removed

    async def async_set_auto_sort(self, entity_id: str, mode: str) -> None:
        if mode == MODE_OFF:
            self._forget(entity_id)
        else:
            entity = _get_entity(self.hass, entity_id)
            if entity is not None and not _supports_move(entity):
                raise _error("cannot_keep_sorted", entity_id)
            self.auto_sort[entity_id] = mode
            # Drop any old subscription so the new mode applies right away.
            if sub := self._subs.pop(entity_id, None):
                sub[1]()
            self._ensure_subscribed(entity_id)
        await self._store.async_save({"auto_sort": self.auto_sort})

    @callback
    def _forget(self, entity_id: str) -> None:
        self.auto_sort.pop(entity_id, None)
        if sub := self._subs.pop(entity_id, None):
            sub[1]()
        if cancel := self._timers.pop(entity_id, None):
            cancel()

    @callback
    def _handle_registry_updated(self, event: Event) -> None:
        """Follow a list that's renamed and forget one that's deleted."""
        action = event.data.get("action")
        entity_id = event.data.get("entity_id", "")
        if action == "remove" and entity_id in self.auto_sort:
            _LOGGER.debug("%s was deleted, dropping its auto-sort", entity_id)
            self._forget(entity_id)
            self._save()
        elif action == "update":
            old_id = event.data.get("old_entity_id")
            if old_id and old_id in self.auto_sort:
                mode = self.auto_sort[old_id]
                self._forget(old_id)
                self.auto_sort[entity_id] = mode
                self._ensure_subscribed(entity_id)
                self._save()

    @callback
    def _prune_missing(self, _hass: HomeAssistant) -> None:
        """Once everything has loaded, drop settings for lists that are gone."""
        registry = er.async_get(self.hass)
        gone = [
            entity_id
            for entity_id in self.auto_sort
            if registry.async_get(entity_id) is None
            and self.hass.states.get(entity_id) is None
        ]
        for entity_id in gone:
            _LOGGER.debug("%s no longer exists, dropping its auto-sort", entity_id)
            self._forget(entity_id)
        if gone:
            self._save()

    @callback
    def _ensure_subscribed(self, entity_id: str) -> None:
        """Subscribe to item updates. Re-subscribes if the entity was recreated."""
        if entity_id not in self.auto_sort:
            return
        entity = _get_entity(self.hass, entity_id)
        if entity is None:
            return  # Not loaded yet; the state listener will catch it later.
        current = self._subs.get(entity_id)
        if current and current[0] is entity:
            return
        if current:
            current[1]()

        @callback
        def _items_changed(_items: Any) -> None:
            self._schedule(entity_id)

        self._subs[entity_id] = (entity, entity.async_subscribe_updates(_items_changed))
        self._schedule(entity_id)

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id", "")
        if entity_id in self.auto_sort:
            self._ensure_subscribed(entity_id)

    @callback
    def _schedule(self, entity_id: str) -> None:
        if cancel := self._timers.pop(entity_id, None):
            cancel()

        @callback
        def _fire(_now: Any) -> None:
            self._timers.pop(entity_id, None)
            self.hass.async_create_task(self._auto_sort(entity_id))

        self._timers[entity_id] = async_call_later(self.hass, AUTO_SORT_DELAY, _fire)

    async def _auto_sort(self, entity_id: str) -> None:
        order = self.auto_sort.get(entity_id)
        entity = _get_entity(self.hass, entity_id)
        if not order or entity is None or not _supports_move(entity):
            return
        lock = self._lock(entity_id)
        if lock.locked():
            # A sort is running; check again once it settles.
            self._schedule(entity_id)
            return
        if is_sorted(list(entity.todo_items or []), order):
            return
        try:
            await self.async_sort(entity_id, order)
        except HomeAssistantError as err:
            # Items can change mid-sort (e.g. deleted from another device).
            _LOGGER.debug("Auto-sort of %s interrupted: %s", entity_id, err)
            self._schedule(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up To-do Sort from the UI."""
    manager = TodoSortManager(hass)
    await manager.async_load()
    hass.data[DOMAIN] = manager

    async def handle_sort(call: ServiceCall) -> None:
        order = call.data.get(ATTR_ORDER, ORDER_ASC)
        if order not in ORDERS:
            raise _error("invalid_order")
        for entity_id in sorted(await _extract_entity_ids(hass, call)):
            await manager.async_sort(entity_id, order)

    async def handle_set_auto_sort(call: ServiceCall) -> None:
        mode = call.data.get(ATTR_MODE, ORDER_ASC)
        if mode not in MODES:
            raise _error("invalid_mode")
        for entity_id in sorted(await _extract_entity_ids(hass, call)):
            await manager.async_set_auto_sort(entity_id, mode)

    async def handle_remove_duplicates(call: ServiceCall) -> ServiceResponse:
        removed = 0
        for entity_id in sorted(await _extract_entity_ids(hass, call)):
            removed += await manager.async_remove_duplicates(entity_id)
        return {"removed": removed} if call.return_response else None

    hass.services.async_register(DOMAIN, SERVICE_SORT, handle_sort)
    hass.services.async_register(DOMAIN, SERVICE_SET_AUTO_SORT, handle_set_auto_sort)
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_DUPLICATES,
        handle_remove_duplicates,
        supports_response=SupportsResponse.OPTIONAL,
    )
    await _async_register_once(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload. The frontend script stays registered until restart."""
    if manager := hass.data.pop(DOMAIN, None):
        manager.async_unload()
    for service in (SERVICE_SORT, SERVICE_SET_AUTO_SORT, SERVICE_REMOVE_DUPLICATES):
        hass.services.async_remove(DOMAIN, service)
    return True


async def _async_register_once(hass: HomeAssistant) -> None:
    """Websocket command and frontend script. These survive an entry reload."""
    flag = f"{DOMAIN}_registered"
    if hass.data.get(flag):
        return
    websocket_api.async_register_command(hass, ws_settings)
    path = Path(__file__).parent / "frontend" / "todo-sort.js"
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(path), False)]
        )
    except ImportError:  # Older than 2024.7
        hass.http.register_static_path(FRONTEND_URL, str(path), False)
    add_extra_js_url(hass, f"{FRONTEND_URL}?v={VERSION}")
    hass.data[flag] = True


@websocket_api.websocket_command({"type": "todo_sort/settings"})
@callback
def ws_settings(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Tell the frontend which lists are kept sorted."""
    manager: TodoSortManager | None = hass.data.get(DOMAIN)
    connection.send_result(
        msg["id"], {"auto_sort": dict(manager.auto_sort) if manager else {}}
    )
