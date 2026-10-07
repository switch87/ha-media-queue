// What the library can do with a browse item, and the messages it sends.

// Media sources without music, and classes/types that are no audio.
const NON_AUDIO_SOURCES = ["camera", "image", "image_upload", "tts", "ai_task"];
const NON_AUDIO_CLASSES = new Set(["image", "video", "movie", "episode", "tv_show", "season", "app"]);

/** Return whether queue actions make sense for an item (audio only). */
export function isAudio(item) {
  const id = item.media_content_id ?? "";
  if (NON_AUDIO_SOURCES.some((source) => id === `media-source://${source}` || id.startsWith(`media-source://${source}/`))) {
    return false;
  }
  const type = item.media_content_type ?? "";
  return !NON_AUDIO_CLASSES.has(item.media_class) && !/^(image|video)\//.test(type) && type !== "app";
}

/** Return which buttons a browse item gets (queue actions only for audio). */
export function itemActions(item) {
  const queueable = Boolean(item.can_play || item.can_expand) && isAudio(item);
  return {
    open: Boolean(item.can_expand),
    play: queueable,
    next: queueable,
    add: queueable,
  };
}

/** Return the websocket message that lists node (null: the root). */
export function browseMessage(entityId, canBrowse, node) {
  const message = canBrowse
    ? { type: "media_player/browse_media", entity_id: entityId }
    : { type: "media_source/browse_media" };
  if (node) {
    message.media_content_id = node.media_content_id;
    if (canBrowse) {
      message.media_content_type = node.media_content_type;
    }
  }
  return message;
}

/** Return the media_queue/add message for item in mode. */
export function addMessage(entityId, item, mode) {
  return {
    type: "media_queue/add",
    entity_id: entityId,
    mode,
    media_content_id: item.media_content_id,
    media_content_type: item.media_content_type ?? "",
    title: item.title ?? null,
    media_class: item.media_class ?? null,
    thumbnail: item.thumbnail ?? null,
    can_expand: Boolean(item.can_expand),
  };
}

/** Return whether a relative HA URL needs a signature (none and no token yet). */
export function needsSigning(url) {
  return (
    typeof url === "string" && url.startsWith("/") && !url.includes("authSig=") && !url.includes("token=")
  );
}

/**
 * Return the key of a note for the listed node, or null. Sonos plays items of
 * its own library and favorites by replacing its own queue each time.
 */
export function sourceNote(entityEntry, node) {
  if (entityEntry?.platform !== "sonos" || !node) {
    return null;
  }
  return node.media_content_id.startsWith("media-source://") ? null : "note_sonos_library";
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/**
 * Return the children to list: local media in natural order ("2" before
 * "10"), folders first, like the queue gets them; other sources as given.
 */
export function sortedChildren(node, children) {
  if (!node?.media_content_id?.startsWith("media-source://media_source/")) {
    return children;
  }
  return [...children].sort(
    (a, b) => Number(!a.can_expand) - Number(!b.can_expand) || collator.compare(a.title, b.title),
  );
}
