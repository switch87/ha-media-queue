// The saved playlists in the panel's library column: nodes, buttons, messages.

export const PLAYLISTS_ID = "media-queue://playlists";
const OWN_SOURCE = "media-source://media_queue";
const NAME_MAX = 100;

/**
 * Return the children to list: at the root a "Playlists" folder first; the
 * integration's own media source is left out everywhere (the folder is better).
 */
export function withPlaylistsFolder(children, node, title) {
  const listed = (children ?? []).filter(
    (child) => child.media_content_id !== OWN_SOURCE && !child.media_content_id.startsWith(`${OWN_SOURCE}/`),
  );
  if (node) {
    return listed;
  }
  return [{ kind: "playlists", media_content_id: PLAYLISTS_ID, title, can_expand: true, can_play: false }, ...listed];
}

/** Return library nodes for the playlist summaries. */
export function playlistNodes(summaries) {
  return summaries.map((summary) => ({
    kind: "playlist",
    playlist_id: summary.id,
    media_content_id: `media-queue://playlist/${summary.id}`,
    title: summary.name,
    count: summary.count,
    readonly: Boolean(summary.readonly),
    can_expand: true,
    can_play: false,
  }));
}

/** Return library nodes for the tracks of a playlist. */
export function trackNodes(playlist) {
  return (playlist.items ?? []).map((item) => ({
    kind: "playlist_item",
    playlist_id: playlist.id,
    item_id: item.id,
    media_content_id: `media-queue://playlist/${playlist.id}/${item.id}`,
    title: item.artist ? `${item.title} – ${item.artist}` : item.title,
    thumbnail: item.thumbnail ?? null,
    can_expand: false,
    can_play: true,
  }));
}

/** Return the buttons of a playlist node, or null for ordinary browse items. */
export function nodeActions(node) {
  const kind = node.kind;
  if (!kind) {
    return null;
  }
  const playable = kind !== "playlists";
  const playlist = kind === "playlist";
  return {
    open: kind !== "playlist_item",
    play: playable,
    next: playable,
    add: playable,
    rename: playlist && !node.readonly,
    remove: playlist && !node.readonly,
  };
}

export const listMessage = () => ({ type: "media_queue/playlists/list" });

export const getMessage = (playlistId) => ({ type: "media_queue/playlists/get", playlist_id: playlistId });

export const saveMessage = (entityId, name, overwrite) => ({
  type: "media_queue/playlists/save",
  entity_id: entityId,
  name,
  overwrite,
});

export const renameMessage = (playlistId, name) => ({
  type: "media_queue/playlists/rename",
  playlist_id: playlistId,
  name,
});

export const deleteMessage = (playlistId) => ({ type: "media_queue/playlists/delete", playlist_id: playlistId });

/** Return the message that loads a playlist (or one of its tracks) in mode. */
export function loadMessage(entityId, node, mode) {
  const message = { type: "media_queue/playlists/load", entity_id: entityId, playlist_id: node.playlist_id, mode };
  if (node.item_id) {
    message.item_id = node.item_id;
  }
  return message;
}

/** Return the trimmed name, or null when it is empty or too long. */
export function cleanName(text) {
  const name = (text ?? "").trim();
  return name && name.length <= NAME_MAX ? name : null;
}

/** Return whether an error says the name belongs to another playlist. */
export function isNameTaken(err) {
  return err?.translation_key === "playlist_exists";
}

/** Return the playlist summary called name (any case), or null. */
export function findByName(summaries, name) {
  const folded = name.toLocaleLowerCase();
  return (summaries ?? []).find((summary) => summary.name.toLocaleLowerCase() === folded) ?? null;
}
