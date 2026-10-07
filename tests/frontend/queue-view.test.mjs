import { test } from "node:test";
import assert from "node:assert/strict";

import { currentItem, queueRows, rowsKey } from "../../custom_components/media_queue/frontend/lib/queue-view.js";

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

test("the rows key follows ids and markers", () => {
  const key = rowsKey(queueRows(snapshot));
  assert.equal(key, "1:c,2:n,3:");
  assert.notEqual(key, rowsKey(queueRows({ ...snapshot, current: 1, next: 2 })));
});

test("the current item", () => {
  assert.equal(currentItem(snapshot).title, "A");
  assert.equal(currentItem({ ...snapshot, current: null }), null);
  assert.equal(currentItem({ ...snapshot, current: 7 }), null);
  assert.equal(currentItem(undefined), null);
});
