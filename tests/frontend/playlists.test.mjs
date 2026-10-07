import { test } from "node:test";
import assert from "node:assert/strict";

import {
  PLAYLISTS_ID,
  cleanName,
  deleteMessage,
  getMessage,
  isNameTaken,
  listMessage,
  loadMessage,
  nodeActions,
  playlistNodes,
  renameMessage,
  saveMessage,
  trackNodes,
  withPlaylistsFolder,
} from "../../custom_components/media_queue/frontend/lib/playlists.js";

const own = { media_content_id: "media-source://media_queue", title: "Playlists (Media queue)" };
const ownChild = { media_content_id: "media-source://media_queue/abc", title: "x" };
const local = { media_content_id: "media-source://media_source", title: "My media" };

test("the root gets a playlists folder first; the own media source is hidden", () => {
  const children = withPlaylistsFolder([own, local], null, "Playlists");
  assert.deepEqual(
    children.map((c) => c.title),
    ["Playlists", "My media"],
  );
  assert.equal(children[0].media_content_id, PLAYLISTS_ID);
  assert.equal(children[0].kind, "playlists");
  assert.equal(children[0].can_expand, true);
  assert.deepEqual(withPlaylistsFolder([ownChild, local], { media_content_id: "x" }, "P"), [local]);
  assert.deepEqual(withPlaylistsFolder(undefined, null, "P").length, 1);
});

test("playlist and track nodes", () => {
  const [node] = playlistNodes([{ id: "p1", name: "Mix", count: 3, duration: 600 }]);
  assert.deepEqual(node, {
    kind: "playlist",
    playlist_id: "p1",
    media_content_id: "media-queue://playlist/p1",
    title: "Mix",
    count: 3,
    can_expand: true,
    can_play: false,
  });
  const tracks = trackNodes({
    id: "p1",
    items: [
      { id: "i1", title: "Song", artist: "Band", thumbnail: "/t.png", media_content_id: "x" },
      { id: "i2", title: "Radio", media_content_id: "http://r" },
    ],
  });
  assert.deepEqual(tracks[0], {
    kind: "playlist_item",
    playlist_id: "p1",
    item_id: "i1",
    media_content_id: "media-queue://playlist/p1/i1",
    title: "Song – Band",
    thumbnail: "/t.png",
    can_expand: false,
    can_play: true,
  });
  assert.equal(tracks[1].title, "Radio");
  assert.equal(tracks[1].thumbnail, null);
  assert.deepEqual(trackNodes({ id: "p", items: undefined }), []);
});

test("which buttons each node gets", () => {
  assert.deepEqual(nodeActions({ kind: "playlists" }), {
    open: true, play: false, next: false, add: false, rename: false, remove: false,
  });
  assert.deepEqual(nodeActions({ kind: "playlist" }), {
    open: true, play: true, next: true, add: true, rename: true, remove: true,
  });
  assert.deepEqual(nodeActions({ kind: "playlist_item" }), {
    open: false, play: true, next: true, add: true, rename: false, remove: false,
  });
  assert.equal(nodeActions({ media_content_id: "x" }), null);
});

test("messages", () => {
  assert.deepEqual(listMessage(), { type: "media_queue/playlists/list" });
  assert.deepEqual(getMessage("p"), { type: "media_queue/playlists/get", playlist_id: "p" });
  assert.deepEqual(saveMessage("media_player.a", "Mix", true), {
    type: "media_queue/playlists/save",
    entity_id: "media_player.a",
    name: "Mix",
    overwrite: true,
  });
  assert.deepEqual(renameMessage("p", "New"), { type: "media_queue/playlists/rename", playlist_id: "p", name: "New" });
  assert.deepEqual(deleteMessage("p"), { type: "media_queue/playlists/delete", playlist_id: "p" });
  assert.deepEqual(loadMessage("media_player.a", { kind: "playlist", playlist_id: "p" }, "next"), {
    type: "media_queue/playlists/load",
    entity_id: "media_player.a",
    playlist_id: "p",
    mode: "next",
  });
  assert.deepEqual(loadMessage("media_player.a", { kind: "playlist_item", playlist_id: "p", item_id: "i" }, "add"), {
    type: "media_queue/playlists/load",
    entity_id: "media_player.a",
    playlist_id: "p",
    mode: "add",
    item_id: "i",
  });
});

test("names are trimmed, 1 to 100 characters", () => {
  assert.equal(cleanName("  Mix "), "Mix");
  assert.equal(cleanName("   "), null);
  assert.equal(cleanName("x".repeat(101)), null);
  assert.equal(cleanName(undefined), null);
});

test("a taken name is recognised in the error", () => {
  assert.equal(isNameTaken({ translation_key: "playlist_exists" }), true);
  assert.equal(isNameTaken({ code: "unauthorized" }), false);
  assert.equal(isNameTaken(undefined), false);
});
