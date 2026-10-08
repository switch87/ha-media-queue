"""Tags read in the background: small batches, one reading at a time per source.

A source is a player's queue or the playlist library; each has its own
TagReader, so a hung network mount pauses only the source that hit it.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Protocol

from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .tags import Tags, read_batch

_LOGGER = logging.getLogger(__name__)

# Files per batch, seconds of reading per batch (smaller batches on a slow
# mount), seconds before a batch counts as hung.
TAG_BATCH = 100
TAG_BUDGET = 2.0
TAG_TIMEOUT = 30
# After a batch timed out (a hung mount), no tags for this source for a while.
TAG_PAUSE = timedelta(minutes=10)

# (item id, media folder, path relative to it)
type TagFile = tuple[str, str, str]


class TagTarget(Protocol):
    """What a TagReader fills in."""

    def tag_ids(self) -> set[str]:
        """Return the ids of the items that are still there."""

    def apply_tags(self, found: dict[str, Tags]) -> bool:
        """Put the tags on the items; return whether any changed."""

    def tags_changed(self) -> None:
        """Tell the world (and the store) that tags were put on items."""


class TagReader:
    """Read the tags of one source's items, batch by batch, in the executor."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        """Create the reader of the source called name (for logs)."""
        self.hass = hass
        self.name = name
        self._lock = asyncio.Lock()
        self._paused_until = dt_util.utcnow()
        self._tasks: set[asyncio.Task[None]] = set()

    @callback
    def start(self, files: list[TagFile], target: TagTarget) -> None:
        """Read the tags of files for target in the background."""
        if not files or dt_util.utcnow() < self._paused_until:
            return
        task = self.hass.async_create_background_task(
            self._read(files, target), f"{DOMAIN} tags {self.name}"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @callback
    def cancel(self) -> None:
        """Stop every reading of this source."""
        for task in self._tasks:
            task.cancel()

    async def _read(self, files: list[TagFile], target: TagTarget) -> None:
        """Read tags batch by batch; each batch updates the target once."""
        async with self._lock:
            while True:
                # Items removed meanwhile (a clear, a replace) are not read.
                present = target.tag_ids()
                files = [file for file in files if file[0] in present]
                if not files:
                    return
                try:
                    count, found = await asyncio.wait_for(
                        self.hass.async_add_executor_job(
                            read_batch, files[:TAG_BATCH], TAG_BUDGET
                        ),
                        TAG_TIMEOUT,
                    )
                except TimeoutError:
                    _LOGGER.warning(
                        "%s: reading tags takes too long; keeping file names "
                        "and reading no tags for it for %s",
                        self.name,
                        TAG_PAUSE,
                    )
                    self._paused_until = dt_util.utcnow() + TAG_PAUSE
                    return
                files = files[count:]
                if target.apply_tags(found):
                    target.tags_changed()
