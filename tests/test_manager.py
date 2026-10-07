"""Tests for the queue manager: persistence and subscribers."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.media_queue.const import (
    PLAYBACK_SAVE_DELAY,
    SAVE_DELAY,
    STORAGE_KEY,
)
from custom_components.media_queue.controller import Change, Phase
from custom_components.media_queue.manager import QueueManager
from custom_components.media_queue.model import Mode, QueueItem

PLAYER = "media_player.living_room"


def _item(title: str) -> QueueItem:
    return QueueItem(
        media_content_id=f"media-source://media_source/local/{title}.mp3",
        media_content_type="audio/mpeg",
        title=title,
        item_id=f"id-{title}",
    )


def _stored(entity_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "queues": {
                entity_id: {
                    "items": [_item("a").as_dict(), _item("b").as_dict()],
                    "current": 1,
                    "next": None,
                    **extra,
                }
            }
        },
    }


async def test_load_restores_queues(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Stored queues come back with their position and phase."""
    hass_storage[STORAGE_KEY] = _stored(PLAYER, phase="playing", fingerprint="x")
    manager = QueueManager(hass)
    await manager.async_load()

    controller = manager.get(PLAYER)
    assert controller is not None
    assert [item.title for item in controller.queue.items] == ["a", "b"]
    assert controller.queue.current == 1
    assert controller.phase is Phase.PLAYING
    assert controller.fingerprint == "x"
    assert manager.entity_ids == [PLAYER]
    assert manager.snapshot(PLAYER)["current"] == 1
    assert manager.snapshot(PLAYER)["next"] is None
    await manager.async_unload()


async def test_load_tolerates_bad_storage(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Malformed stored data gives empty or repaired queues, never an error."""
    data = _stored(PLAYER, phase="dancing", fingerprint=7)
    data["data"]["queues"]["sensor.not_a_player"] = {"items": []}
    data["data"]["queues"][3] = {}
    hass_storage[STORAGE_KEY] = data
    manager = QueueManager(hass)
    await manager.async_load()

    controller = manager.get(PLAYER)
    assert controller is not None
    assert controller.phase is Phase.IDLE
    assert controller.fingerprint is None
    assert manager.entity_ids == [PLAYER]
    await manager.async_unload()


async def test_load_without_queues_dict(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Storage without a queues mapping is ignored."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"queues": []},
    }
    manager = QueueManager(hass)
    await manager.async_load()
    assert manager.entity_ids == []
    await manager.async_unload()


async def test_load_empty(hass: HomeAssistant) -> None:
    """Nothing stored: no queues."""
    manager = QueueManager(hass)
    await manager.async_load()
    assert manager.get(PLAYER) is None
    assert manager.entity_ids == []
    await manager.async_unload()


async def test_starting_phase_is_not_restored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A play that was in progress at shutdown is not followed after it."""
    hass_storage[STORAGE_KEY] = _stored(PLAYER, phase="starting")
    manager = QueueManager(hass)
    await manager.async_load()
    controller = manager.get(PLAYER)
    assert controller is not None
    assert controller.phase is Phase.IDLE
    await manager.async_unload()


async def test_changes_are_saved_delayed(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A change is written after the save delay, empty queues are left out."""
    manager = QueueManager(hass)
    await manager.async_load()
    controller = manager.controller(PLAYER)
    controller.queue.add([_item("a")], Mode.ADD, limit=10)
    manager.controller("media_player.kitchen")
    controller.async_changed()
    assert STORAGE_KEY not in hass_storage

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()

    assert hass_storage[STORAGE_KEY]["data"] == {
        "queues": {
            PLAYER: {
                "items": [_item("a").as_dict()],
                "current": None,
                "next": None,
                "phase": "idle",
                "fingerprint": None,
            }
        }
    }
    await manager.async_unload()


async def test_unload_flushes(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Unloading writes pending changes at once."""
    manager = QueueManager(hass)
    await manager.async_load()
    controller = manager.controller(PLAYER)
    controller.queue.add([_item("a")], Mode.ADD, limit=10)
    controller.async_changed()
    await manager.async_unload()
    assert hass_storage[STORAGE_KEY]["data"]["queues"][PLAYER]["items"]


async def test_controller_is_created_once(hass: HomeAssistant) -> None:
    """The same entity gets the same controller."""
    manager = QueueManager(hass)
    await manager.async_load()
    assert manager.controller(PLAYER) is manager.controller(PLAYER)
    await manager.async_unload()


async def test_subscribers_get_snapshots(hass: HomeAssistant) -> None:
    """Subscribers of an entity hear about its changes until they unsubscribe."""
    manager = QueueManager(hass)
    await manager.async_load()
    seen: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    unsubscribe = manager.subscribe(PLAYER, seen.append)
    manager.subscribe("media_player.kitchen", other.append)

    controller = manager.controller(PLAYER)
    controller.queue.add([_item("a")], Mode.ADD, limit=10)
    controller.async_changed()

    assert seen == [
        {
            "entity_id": PLAYER,
            "items": [_item("a").as_dict()],
            "current": None,
            "next": 0,
            "phase": "idle",
            "last_error": None,
        }
    ]
    assert other == []
    unsubscribe()
    unsubscribe()  # twice is harmless
    controller.async_changed()
    assert len(seen) == 1
    await manager.async_unload()


async def test_snapshot_of_unknown_entity(hass: HomeAssistant) -> None:
    """An entity without a queue has an empty snapshot."""
    manager = QueueManager(hass)
    await manager.async_load()
    assert manager.snapshot(PLAYER) == {
        "entity_id": PLAYER,
        "items": [],
        "current": None,
        "next": None,
        "phase": "idle",
        "last_error": None,
    }
    await manager.async_unload()


async def test_unload_closes_subscriptions_and_ignores_late_changes(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """After unloading, subscribers are told and changes are not saved."""
    manager = QueueManager(hass)
    await manager.async_load()
    closed: list[bool] = []
    seen: list[dict[str, Any]] = []
    manager.subscribe(PLAYER, seen.append, lambda: closed.append(True))
    controller = manager.controller(PLAYER)
    await manager.async_unload()
    assert closed == [True]

    controller.queue.add([_item("late")], Mode.ADD, limit=10)
    controller.async_changed()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()
    assert seen == []
    assert hass_storage[STORAGE_KEY]["data"] == {"queues": {}}


async def test_playback_changes_send_small_events_and_save_rarely(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Phase churn: a small event, no write; a new current: a late write."""
    manager = QueueManager(hass)
    await manager.async_load()
    seen: list[dict[str, Any]] = []
    manager.subscribe(PLAYER, seen.append)
    controller = manager.controller(PLAYER)
    controller.queue.add([_item("a"), _item("b")], Mode.ADD, limit=10)
    controller.async_changed()
    assert "items" in seen[-1]
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    hass_storage.pop(STORAGE_KEY)

    controller.phase = Phase.STOPPED
    controller.async_changed(Change.PLAYBACK)
    assert seen[-1] == {
        "entity_id": PLAYER,
        "playback": True,
        "current": None,
        "next": 0,
        "phase": "stopped",
        "last_error": None,
    }
    freezer.tick(timedelta(seconds=PLAYBACK_SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert STORAGE_KEY not in hass_storage  # phase churn is not written

    controller.queue.set_current(1)
    controller.async_changed(Change.CURRENT)
    assert seen[-1]["current"] == 1
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert STORAGE_KEY not in hass_storage  # a new current waits longer
    freezer.tick(timedelta(seconds=PLAYBACK_SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[STORAGE_KEY]["data"]["queues"][PLAYER]["current"] == 1
    await manager.async_unload()


async def test_current_change_does_not_delay_a_queue_save(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A queue edit is written soon even when playback changes follow."""
    manager = QueueManager(hass)
    await manager.async_load()
    controller = manager.controller(PLAYER)
    controller.queue.add([_item("a")], Mode.ADD, limit=10)
    controller.async_changed()
    controller.queue.set_current(0)
    controller.async_changed(Change.CURRENT)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()
    assert hass_storage[STORAGE_KEY]["data"]["queues"][PLAYER]["current"] == 0
    await manager.async_unload()
