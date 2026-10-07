import { test } from "node:test";
import assert from "node:assert/strict";

import { FEATURE } from "../../custom_components/media_queue/frontend/lib/players.js";
import {
  nowPlaying,
  playPauseAction,
  queueButtons,
  repeatButton,
  shuffleButton,
  volumeOf,
} from "../../custom_components/media_queue/frontend/lib/transport.js";

const player = (state, features, attrs = {}) => ({
  entity_id: "media_player.a",
  state,
  attributes: { supported_features: features, ...attrs },
});
const queue = (items, current, next) => ({ items: items.map((title, i) => ({ id: String(i), title })), current, next });

test("play/pause acts on the player while it plays or is paused", () => {
  assert.deepEqual(playPauseAction(player("playing", FEATURE.PAUSE), queue([], null, null)), {
    kind: "service",
    service: "media_pause",
    icon: "mdi:pause",
  });
  assert.equal(playPauseAction(player("playing", 0), null).service, "media_stop");
  assert.deepEqual(playPauseAction(player("paused", FEATURE.PLAY), null), {
    kind: "service",
    service: "media_play",
    icon: "mdi:play",
  });
});

test("otherwise play/pause starts the queue where it is", () => {
  assert.deepEqual(playPauseAction(player("idle", 0), queue(["a", "b"], 1, null)), {
    kind: "queue",
    index: 1,
    icon: "mdi:play",
  });
  assert.equal(playPauseAction(player("off", 0), queue(["a", "b"], null, 1)).index, 1);
  assert.equal(playPauseAction(player("paused", 0), queue(["a"], null, null)).index, 0);
  assert.equal(playPauseAction(undefined, queue([], null, null)), null);
  assert.equal(playPauseAction(player("idle", 0), undefined), null);
});

test("previous needs items, next needs a next item", () => {
  assert.deepEqual(queueButtons(queue(["a", "b"], 0, 1)), { previous: true, next: true });
  assert.deepEqual(queueButtons(queue(["a"], 0, null)), { previous: true, next: false });
  assert.deepEqual(queueButtons(undefined), { previous: false, next: false });
});

test("volume only for players that can set it", () => {
  assert.equal(volumeOf(player("idle", FEATURE.VOLUME_SET, { volume_level: 0.456 })), 46);
  assert.equal(volumeOf(player("idle", FEATURE.VOLUME_SET)), 0);
  assert.equal(volumeOf(player("idle", 0, { volume_level: 0.5 })), null);
});

test("now playing prefers the player's info, then the queue", () => {
  const playing = player("playing", 0, {
    media_title: "Live",
    media_artist: "Amon Düül II",
    media_album_name: "Yeti",
    entity_picture: "/pic",
  });
  assert.deepEqual(nowPlaying(playing, queue(["a"], 0, null)), {
    title: "Live",
    subtitle: "Amon Düül II – Yeti",
    picture: "/pic",
  });
  assert.deepEqual(nowPlaying(player("idle", 0, { media_title: "old" }), queue(["a"], 0, null)), {
    title: "a",
    subtitle: "",
    picture: null,
  });
  assert.deepEqual(nowPlaying(player("buffering", 0), queue([], null, null)), {
    title: null,
    subtitle: "",
    picture: null,
  });
  assert.deepEqual(nowPlaying(undefined, undefined), { title: null, subtitle: "", picture: null });
});

test("next wraps with repeat all", () => {
  assert.deepEqual(queueButtons({ ...queue(["a"], 0, null), repeat: "all" }), { previous: true, next: true });
  assert.deepEqual(queueButtons({ ...queue([], null, null), repeat: "all" }), { previous: false, next: false });
});

test("the shuffle button toggles and shows its state", () => {
  assert.deepEqual(shuffleButton({ ...queue(["a"], 0, null), shuffle: true }), {
    pressed: true,
    icon: "mdi:shuffle-variant",
    title: "shuffle_on",
    value: false,
  });
  assert.deepEqual(shuffleButton(queue(["a"], 0, null)), {
    pressed: false,
    icon: "mdi:shuffle-disabled",
    title: "shuffle_off",
    value: true,
  });
  assert.equal(shuffleButton(undefined).value, true);
});

test("the repeat button cycles off, all, one; its name carries the state", () => {
  assert.deepEqual(repeatButton(undefined), { icon: "mdi:repeat-off", title: "repeat_off", value: "all" });
  assert.deepEqual(repeatButton({ repeat: "all" }), { icon: "mdi:repeat", title: "repeat_all", value: "one" });
  assert.deepEqual(repeatButton({ repeat: "one" }), { icon: "mdi:repeat-once", title: "repeat_one", value: "off" });
  assert.equal(repeatButton({ repeat: "twice" }).value, "all");
});

test("now playing from the queue shows the tags", () => {
  const tagged = { items: [{ id: "1", title: "Song", artist: "Band", album: "Record" }], current: 0 };
  assert.deepEqual(nowPlaying(player("idle", 0), tagged), { title: "Song", subtitle: "Band – Record", picture: null });
});
