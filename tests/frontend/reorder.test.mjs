import { test } from "node:test";
import assert from "node:assert/strict";

import { dropIndex, rowAt } from "../../custom_components/media_queue/frontend/lib/reorder.js";

test("dropping above or below a row gives the final index", () => {
  // a b c d e, drag b (1)
  assert.equal(dropIndex(1, 3, true, 5), 2); // above d: a c b d e
  assert.equal(dropIndex(1, 3, false, 5), 3); // below d: a c d b e
  assert.equal(dropIndex(1, 0, true, 5), 0); // above a
  assert.equal(dropIndex(3, 0, false, 5), 1); // d below a
  assert.equal(dropIndex(1, 4, false, 5), 4); // to the end
});

test("drops that change nothing give null", () => {
  assert.equal(dropIndex(1, 1, true, 5), null);
  assert.equal(dropIndex(1, 1, false, 5), null);
  assert.equal(dropIndex(1, 0, false, 5), null); // below a = where b is
  assert.equal(dropIndex(1, 2, true, 5), null); // above c = where b is
});

test("indexes outside the list give null", () => {
  assert.equal(dropIndex(-1, 0, true, 5), null);
  assert.equal(dropIndex(5, 0, true, 5), null);
  assert.equal(dropIndex(0, -1, true, 5), null);
  assert.equal(dropIndex(0, 5, true, 5), null);
});

test("the row under the pointer, and which half", () => {
  const boxes = [
    { top: 0, bottom: 40 },
    { top: 40, bottom: 80 },
  ];
  assert.deepEqual(rowAt(boxes, -5), { index: 0, before: true });
  assert.deepEqual(rowAt(boxes, 30), { index: 0, before: false });
  assert.deepEqual(rowAt(boxes, 45), { index: 1, before: true });
  assert.deepEqual(rowAt(boxes, 500), { index: 1, before: false });
  assert.equal(rowAt([], 10), null);
});
