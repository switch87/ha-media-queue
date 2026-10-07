import { test } from "node:test";
import assert from "node:assert/strict";

import { limiter } from "../../custom_components/media_queue/frontend/lib/limiter.js";

test("at most n jobs run at once, all finish in order of start", async () => {
  const run = limiter(2);
  let active = 0;
  let peak = 0;
  const done = [];
  const job = (name, fail = false) => async () => {
    active += 1;
    peak = Math.max(peak, active);
    await new Promise((resolve) => setTimeout(resolve, 5));
    active -= 1;
    done.push(name);
    if (fail) throw new Error(name);
    return name;
  };
  const results = await Promise.allSettled([run(job("a")), run(job("b", true)), run(job("c")), run(job("d"))]);
  assert.equal(peak, 2);
  assert.deepEqual(done.sort(), ["a", "b", "c", "d"]);
  assert.equal(results[0].value, "a");
  assert.equal(results[1].status, "rejected");
  assert.equal(results[3].value, "d");
});
