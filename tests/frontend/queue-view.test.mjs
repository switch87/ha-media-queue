import { test } from "node:test";
import assert from "node:assert/strict";

import {
  applyUpdate,
  currentItem,
  errorText,
  fileName,
  idsKey,
  newError,
  queueRows,
} from "../../custom_components/media_queue/frontend/lib/queue-view.js";

const snapshot = {
  entity_id: "media_player.a",
  items: [
    { id: "1", title: "A", media_class: "music", thumbnail: "/a.jpg" },
    { id: "2", title: "B" },
    { id: "3", title: "C" },
  ],
  current: 0,
  next: 1,
  phase: "playing",
};

test("rows mark the current and the next item", () => {
  const rows = queueRows(snapshot);
  assert.deepEqual(rows[0], {
    index: 0,
    id: "1",
    title: "A",
    label: "A",
    tooltip: "A",
    thumbnail: "/a.jpg",
    mediaClass: "music",
    current: true,
    next: false,
  });
  assert.equal(rows[1].next, true);
  assert.equal(rows[1].thumbnail, null);
  assert.equal(rows[1].mediaClass, null);
  assert.equal(rows[2].current, false);
  assert.deepEqual(queueRows(undefined), []);
});

test("the current item", () => {
  assert.equal(currentItem(snapshot).title, "A");
  assert.equal(currentItem({ ...snapshot, current: null }), null);
  assert.equal(currentItem({ ...snapshot, current: 7 }), null);
  assert.equal(currentItem(undefined), null);
});

test("a new playback error is shown once, not the one present at load", () => {
  const error = { kind: "did_not_start", title: "B", message: "", at: "t1" };
  assert.equal(newError(null, { last_error: error }, true), null);
  assert.deepEqual(newError(null, { last_error: error }, false), error);
  assert.equal(newError("t1", { last_error: error }, false), null);
  assert.equal(newError("t1", { last_error: null }, false), null);
  assert.equal(newError(null, undefined, false), null);
});

test("error text per kind", () => {
  const t = (key, params) => `${key}:${JSON.stringify(params)}`;
  assert.equal(
    errorText(t, { kind: "did_not_start", title: "B", message: "" }),
    'error_did_not_start:{"title":"B","message":""}',
  );
  assert.equal(
    errorText(t, { kind: "cannot_play", title: "B", message: "down" }),
    'error_cannot_play:{"title":"B","message":"down"}',
  );
});

test("a playback update changes only position, phase and error", () => {
  const base = {
    entity_id: "media_player.a",
    items: [{ id: "1" }, { id: "2" }],
    current: 0,
    next: 1,
    phase: "playing",
    last_error: null,
  };
  const merged = applyUpdate(base, {
    entity_id: "media_player.a",
    playback: true,
    current: 1,
    next: null,
    phase: "stopped",
    last_error: null,
  });
  assert.deepEqual(merged, { ...base, current: 1, next: null, phase: "stopped" });
  assert.equal(merged.items, base.items);
  assert.equal(applyUpdate(base, { ...base, items: [] }).items.length, 0);
  assert.equal(applyUpdate(null, { playback: true, current: 0 }), null);
});

test("the ids key ignores markers", () => {
  const rows = queueRows({ items: [{ id: "1" }, { id: "2" }], current: 0, next: 1 });
  const moved = queueRows({ items: [{ id: "1" }, { id: "2" }], current: 1, next: null });
  assert.equal(idsKey(rows), idsKey(moved));
  assert.notEqual(idsKey(rows), idsKey(queueRows({ items: [{ id: "2" }, { id: "1" }] })));
});

test("rows show title – artist, the file name as tooltip", () => {
  const [row, plain] = queueRows({
    items: [
      {
        id: "1",
        title: "Soap Shop Rock",
        artist: "Amon Düül II",
        media_content_id: "media-source://media_source/local/Yeti/01%20Soap.mp3",
      },
      { id: "2", title: "Radio", media_content_id: "http://radio/stream" },
    ],
    current: null,
    next: 0,
  });
  assert.equal(row.label, "Soap Shop Rock – Amon Düül II");
  assert.equal(row.tooltip, "01 Soap.mp3");
  assert.equal(plain.label, "Radio");
  assert.equal(plain.tooltip, "Radio");
});

test("file names of local media only, also when badly encoded", () => {
  assert.equal(fileName("media-source://media_source/local/A/b c.mp3"), "b c.mp3");
  assert.equal(fileName("media-source://media_source/local/A/100%.mp3"), "100%.mp3");
  assert.equal(fileName("media-source://media_source/local/"), null);
  assert.equal(fileName("media-source://media_source/local"), null);
  assert.equal(fileName("media-source://radio_browser/x"), null);
  assert.equal(fileName(undefined), null);
});

test("the key changes when a title arrives from the tags", () => {
  const before = queueRows({ items: [{ id: "1", title: "01.mp3" }] });
  const after = queueRows({ items: [{ id: "1", title: "Song", artist: "Band" }] });
  assert.notEqual(idsKey(before), idsKey(after));
});

test("a playback update keeps shuffle and repeat", () => {
  const base = { items: [], current: null, next: null, shuffle: true, repeat: "one" };
  const merged = applyUpdate(base, { playback: true, current: 0, next: null, phase: "idle", last_error: null });
  assert.equal(merged.shuffle, true);
  assert.equal(merged.repeat, "one");
});
