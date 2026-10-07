// What the library can do with a browse item, and the messages it sends.

/** Return which buttons a browse item gets. */
export function itemActions(item) {
  const queueable = Boolean(item.can_play || item.can_expand);
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
