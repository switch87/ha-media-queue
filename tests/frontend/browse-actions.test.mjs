import { test } from "node:test";
import assert from "node:assert/strict";

import { addMessage, browseMessage, itemActions, needsSigning, sourceNote } from "../../custom_components/media_queue/frontend/lib/browse-actions.js";

test("folders can be opened and queued, tracks only queued", () => {
  assert.deepEqual(itemActions({ can_expand: true, can_play: false }), {
    open: true,
    play: true,
    next: true,
    add: true,
  });
  assert.deepEqual(itemActions({ can_expand: false, can_play: true }), {
    open: false,
    play: true,
    next: true,
    add: true,
  });
  assert.deepEqual(itemActions({ can_expand: false, can_play: false }), {
    open: false,
    play: false,
    next: false,
    add: false,
  });
});

test("players that browse use their own tree, others the media sources", () => {
  assert.deepEqual(browseMessage("media_player.a", true, null), {
    type: "media_player/browse_media",
    entity_id: "media_player.a",
  });
  assert.deepEqual(
    browseMessage("media_player.a", true, { media_content_id: "x", media_content_type: "album" }),
    {
      type: "media_player/browse_media",
      entity_id: "media_player.a",
      media_content_id: "x",
      media_content_type: "album",
    },
  );
  assert.deepEqual(browseMessage("media_player.a", false, null), { type: "media_source/browse_media" });
  assert.deepEqual(
    browseMessage("media_player.a", false, { media_content_id: "media-source://x", media_content_type: "" }),
    { type: "media_source/browse_media", media_content_id: "media-source://x" },
  );
});

test("the add message carries what the backend needs", () => {
  const folder = {
    media_content_id: "media-source://media_source/local/Yeti",
    media_content_type: "",
    title: "Yeti",
    media_class: "directory",
    thumbnail: null,
    can_expand: true,
    can_play: false,
  };
  assert.deepEqual(addMessage("media_player.a", folder, "replace"), {
    type: "media_queue/add",
    entity_id: "media_player.a",
    mode: "replace",
    media_content_id: "media-source://media_source/local/Yeti",
    media_content_type: "",
    title: "Yeti",
    media_class: "directory",
    thumbnail: null,
    can_expand: true,
  });
  assert.deepEqual(addMessage("media_player.a", { media_content_id: "x" }, "add"), {
    type: "media_queue/add",
    entity_id: "media_player.a",
    mode: "add",
    media_content_id: "x",
    media_content_type: "",
    title: null,
    media_class: null,
    thumbnail: null,
    can_expand: false,
  });
});

test("only unsigned local thumbnails need signing", () => {
  assert.equal(needsSigning("/api/media_player_proxy/x"), true);
  assert.equal(needsSigning("/api/x?authSig=abc"), false);
  assert.equal(needsSigning("/api/media_player_proxy/media_player.a?token=t&cache=1"), false);
  assert.equal(needsSigning("https://img/x.jpg"), false);
  assert.equal(needsSigning(null), false);
});

test("a note on Sonos's own library and favorites, nowhere else", () => {
  const sonos = { platform: "sonos" };
  assert.equal(sourceNote(sonos, { media_content_id: "A:ALBUM/Yeti" }), "note_sonos_library");
  assert.equal(sourceNote(sonos, { media_content_id: "media-source://media_source/local" }), null);
  assert.equal(sourceNote(sonos, null), null);
  assert.equal(sourceNote({ platform: "mpd" }, { media_content_id: "Yeti" }), null);
  assert.equal(sourceNote(undefined, { media_content_id: "x" }), null);
});
