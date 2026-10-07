import { test } from "node:test";
import assert from "node:assert/strict";

import { languageOf, translate, STRINGS } from "../../custom_components/media_queue/frontend/lib/i18n.js";

test("Dutch for nl and nl-BE, English otherwise", () => {
  assert.equal(languageOf({ language: "nl" }), "nl");
  assert.equal(languageOf({ language: "nl-BE" }), "nl");
  assert.equal(languageOf({ language: "de" }), "en");
  assert.equal(languageOf({ locale: { language: "nl" } }), "nl");
  assert.equal(languageOf(undefined), "en");
  assert.equal(languageOf({}), "en");
});

test("placeholders are filled, missing ones stay visible", () => {
  assert.equal(translate("nl", "items", { count: 3 }), "3 items");
  assert.equal(translate("en", "truncated", { limit: 1000 }), "Only the first 1000 items were added.");
  assert.equal(translate("en", "truncated"), "Only the first {limit} items were added.");
});

test("unknown keys fall back to English, then to the key", () => {
  const saved = STRINGS.nl.only_english;
  STRINGS.en.only_english = "English";
  try {
    assert.equal(translate("nl", "only_english"), "English");
  } finally {
    delete STRINGS.en.only_english;
    assert.equal(saved, undefined);
  }
  assert.equal(translate("nl", "no_such_key"), "no_such_key");
  assert.equal(translate("fr", "queue"), "Queue");
});

test("both languages have the same keys and placeholders", () => {
  assert.deepEqual(Object.keys(STRINGS.nl).sort(), Object.keys(STRINGS.en).sort());
  for (const [key, text] of Object.entries(STRINGS.en)) {
    const holes = (s) => (s.match(/\{\w+\}/g) || []).sort();
    assert.deepEqual(holes(STRINGS.nl[key]), holes(text), key);
  }
});

test("labels of the shuffle and repeat buttons", () => {
  for (const key of ["shuffle", "shuffle_on", "shuffle_off", "repeat_off", "repeat_all", "repeat_one", "shuffled"]) {
    assert.notEqual(translate("en", key), key, key);
  }
  assert.equal(translate("nl", "repeat_one"), "Herhalen: huidig item");
  assert.equal(translate("en", "shuffle_on"), "Shuffle: on");
});

test("labels of the playlist library", () => {
  for (const key of [
    "playlists",
    "save_playlist",
    "playlist_name",
    "save",
    "cancel",
    "overwrite",
    "overwrite_question",
    "saved",
    "rename",
    "renamed",
    "delete",
    "delete_question",
    "deleted",
    "invalid_name",
    "no_playlists",
  ]) {
    assert.notEqual(translate("en", key), key, key);
  }
  assert.equal(translate("nl", "playlists"), "Afspeellijsten");
  assert.equal(translate("en", "overwrite_question", { name: "Mix" }), "A playlist called “Mix” already exists. Overwrite it?");
});
