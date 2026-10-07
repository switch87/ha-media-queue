import { test } from "node:test";
import assert from "node:assert/strict";

import { FEATURE, listPlayers, playersKey, supports } from "../../custom_components/media_queue/frontend/lib/players.js";

const player = (id, features, name) => ({
  entity_id: id,
  state: "idle",
  attributes: { supported_features: features, ...(name ? { friendly_name: name } : {}) },
});

test("only media players that can play media, sorted by name", () => {
  const states = {
    "media_player.werkplaats": player("media_player.werkplaats", FEATURE.PLAY_MEDIA | FEATURE.BROWSE_MEDIA, "Werkplaats"),
    "media_player.living": player("media_player.living", FEATURE.PLAY_MEDIA, "Living Room"),
    "media_player.tv": player("media_player.tv", FEATURE.PAUSE, "TV"),
    "media_player.b": player("media_player.b", FEATURE.PLAY_MEDIA, "Same"),
    "media_player.a": player("media_player.a", FEATURE.PLAY_MEDIA, "Same"),
    "media_player.noname": player("media_player.noname", FEATURE.PLAY_MEDIA),
    "light.kitchen": player("light.kitchen", FEATURE.PLAY_MEDIA, "Kitchen"),
  };
  const players = listPlayers(states);
  assert.deepEqual(
    players.map((p) => p.entityId),
    ["media_player.living", "media_player.noname", "media_player.a", "media_player.b", "media_player.werkplaats"],
  );
  assert.equal(players[0].name, "Living Room");
  assert.equal(players[0].canBrowse, false);
  assert.equal(players[4].canBrowse, true);
  assert.equal(players[1].name, "media_player.noname");
});

test("no states, no players", () => {
  assert.deepEqual(listPlayers(undefined), []);
});

test("supports tolerates missing attributes", () => {
  assert.equal(supports(undefined, FEATURE.PAUSE), false);
  assert.equal(supports({ attributes: {} }, FEATURE.PAUSE), false);
  assert.equal(supports({ attributes: { supported_features: 1 } }, FEATURE.PAUSE), true);
});

test("the key changes only when the list changes", () => {
  const a = [{ entityId: "media_player.a", name: "A", canBrowse: true }];
  assert.equal(playersKey(a), playersKey([{ ...a[0] }]));
  assert.notEqual(playersKey(a), playersKey([{ ...a[0], name: "B" }]));
});
