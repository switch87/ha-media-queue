import { test } from "node:test";
import assert from "node:assert/strict";

import {
  addUrlMessage,
  cleanUrl,
  saveStreamMessage,
  suggestName,
} from "../../custom_components/media_queue/frontend/lib/streams.js";

test("only http and https addresses with a host", () => {
  assert.equal(cleanUrl("  https://radio.example/live  "), "https://radio.example/live");
  assert.equal(cleanUrl("HTTP://radio.example"), "HTTP://radio.example");
  for (const bad of [
    "",
    null,
    undefined,
    "radio.example/live",
    "file:///etc/passwd",
    "media-source://media_source/local/a.mp3",
    "http://",
    "https:///path",
    "http://radio.example/a b",
    `http://radio.example/${"x".repeat(2000)}`,
  ]) {
    assert.equal(cleanUrl(bad), null, String(bad));
  }
});

test("a name suggested from the address", () => {
  assert.equal(suggestName("http://radio.example/live/Radio%20One.m3u"), "Radio One.m3u");
  assert.equal(suggestName("http://radio.example/"), "radio.example");
  assert.equal(suggestName("http://radio.example"), "radio.example");
  assert.equal(suggestName("http://radio.example/%E0%A4%A"), "%E0%A4%A"); // broken escape
});

test("messages", () => {
  assert.deepEqual(addUrlMessage("media_player.a", "http://r/x", "next"), {
    type: "media_queue/add_url",
    entity_id: "media_player.a",
    url: "http://r/x",
    mode: "next",
  });
  assert.deepEqual(saveStreamMessage("http://r/x", "Radio", false), {
    type: "media_queue/streams/save",
    url: "http://r/x",
    name: "Radio",
    overwrite: false,
  });
});
