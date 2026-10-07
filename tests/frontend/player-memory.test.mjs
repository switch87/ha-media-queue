import { test } from "node:test";
import assert from "node:assert/strict";

import { STORAGE_KEY, rememberPlayer, restorePlayer } from "../../custom_components/media_queue/frontend/lib/player-memory.js";

const players = [{ entityId: "media_player.a" }, { entityId: "media_player.b" }];

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, value),
  };
}

const broken = {
  getItem() {
    throw new Error("blocked");
  },
  setItem() {
    throw new Error("blocked");
  },
};

test("the remembered player comes back", () => {
  const storage = memoryStorage();
  rememberPlayer(storage, "media_player.b");
  assert.equal(storage.getItem(STORAGE_KEY), "media_player.b");
  assert.equal(restorePlayer(storage, players), "media_player.b");
});

test("a player that is gone falls back to the first one", () => {
  const storage = memoryStorage();
  rememberPlayer(storage, "media_player.gone");
  assert.equal(restorePlayer(storage, players), "media_player.a");
  assert.equal(restorePlayer(storage, []), null);
});

test("missing or blocked storage is harmless", () => {
  rememberPlayer(broken, "media_player.b");
  rememberPlayer(undefined, "media_player.b");
  assert.equal(restorePlayer(broken, players), "media_player.a");
  assert.equal(restorePlayer(undefined, players), "media_player.a");
});
