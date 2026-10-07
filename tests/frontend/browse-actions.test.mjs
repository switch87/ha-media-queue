import { test } from "node:test";
import assert from "node:assert/strict";

import { addMessage, browseMessage, itemActions, needsSigning, sortedChildren, sourceNote } from "../../custom_components/media_queue/frontend/lib/browse-actions.js";

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

test("local media is listed in natural order, folders first; others as given", () => {
  const local = { media_content_id: "media-source://media_source/local/x" };
  const children = [
    { title: "10 Ten.mp3", can_expand: false },
    { title: "CD 2", can_expand: true },
    { title: "2 Two.mp3", can_expand: false },
    { title: "CD 10", can_expand: true },
  ];
  assert.deepEqual(
    sortedChildren(local, children).map((c) => c.title),
    ["CD 2", "CD 10", "2 Two.mp3", "10 Ten.mp3"],
  );
  const sonos = { media_content_id: "A:ALBUM/x" };
  assert.deepEqual(sortedChildren(sonos, children), children);
  assert.deepEqual(sortedChildren(null, children), children);
});

test("queue actions only for audio: not on non-audio sources, images, video or app roots", () => {
  const none = { open: true, play: false, next: false, add: false };
  const folder = (id, extra = {}) => ({ media_content_id: id, can_expand: true, can_play: false, media_class: "directory", media_content_type: "", ...extra });
  for (const id of [
    "media-source://camera",
    "media-source://camera/camera.door",
    "media-source://image",
    "media-source://image_upload/x",
    "media-source://tts",
    "media-source://ai_task/x",
  ]) {
    assert.deepEqual(itemActions(folder(id)), none, id);
  }
  assert.deepEqual(itemActions(folder("media-source://media_source", { media_class: "app", media_content_type: "app" })), none);
  assert.deepEqual(
    itemActions({ media_content_id: "media-source://media_source/local/x.mp4", can_play: true, can_expand: false, media_class: "video", media_content_type: "video/mp4" }),
    { open: false, play: false, next: false, add: false },
  );
  assert.deepEqual(
    itemActions({ media_content_id: "x.jpg", can_play: true, can_expand: false, media_class: "image", media_content_type: "image/jpeg" }),
    { open: false, play: false, next: false, add: false },
  );
  assert.equal(itemActions({ media_content_id: "x", can_play: true, media_class: "music", media_content_type: "video/mp4" }).play, false);
  assert.equal(itemActions(folder("media-source://cameras_and_more")).play, true);
  assert.equal(itemActions(folder("media-source://media_source/local/Yeti")).play, true);
  assert.equal(itemActions({ media_content_id: "A:ALBUM/Yeti", can_play: true, can_expand: true, media_class: "album", media_content_type: "album" }).add, true);
});
