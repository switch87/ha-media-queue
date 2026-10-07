// What the queue list shows, from a media_queue snapshot.

/** Return the rows of the queue. */
export function queueRows(snapshot) {
  const items = snapshot?.items ?? [];
  return items.map((item, index) => ({
    index,
    id: item.id,
    title: item.title,
    label: labelOf(item),
    tooltip: fileName(item.media_content_id) ?? labelOf(item),
    thumbnail: item.thumbnail ?? null,
    mediaClass: item.media_class ?? null,
    current: index === snapshot.current,
    next: index === snapshot.next,
  }));
}

/** Return the item playing (or last played) from the queue, if any. */
export function currentItem(snapshot) {
  const index = snapshot?.current;
  return index === null || index === undefined ? null : snapshot.items[index] ?? null;
}

/**
 * Return the playback error to show: a new one since lastAt, never the one
 * already present in the first snapshot after opening the panel.
 */
export function newError(lastAt, snapshot, first) {
  const error = snapshot?.last_error ?? null;
  if (first || !error || error.at === lastAt) {
    return null;
  }
  return error;
}

/** Return the message for a playback error (t translates a key). */
export function errorText(t, error) {
  return t(`error_${error.kind}`, { title: error.title, message: error.message });
}

/** Return the snapshot after an update: a full snapshot or a playback-only one. */
export function applyUpdate(snapshot, update) {
  if (!update.playback) {
    return update;
  }
  if (!snapshot) {
    return null;
  }
  return {
    ...snapshot,
    current: update.current,
    next: update.next,
    phase: update.phase,
    last_error: update.last_error,
  };
}

/** Return a key of the items and their labels (markers change in place). */
export function idsKey(rows) {
  return rows.map((r) => `${r.id}\u0000${r.label}`).join("\u0001");
}

const LOCAL_MEDIA = "media-source://media_source/";

/** Return the file name of a local media item's id, else null. */
export function fileName(contentId) {
  if (!contentId?.startsWith(LOCAL_MEDIA)) {
    return null;
  }
  const rest = contentId.slice(LOCAL_MEDIA.length);
  const slash = rest.indexOf("/");
  const name = slash < 0 ? "" : rest.slice(slash + 1).split("/").pop();
  if (!name) {
    return null;
  }
  try {
    return decodeURIComponent(name);
  } catch {
    return name; // a "%" that is no escape
  }
}

/** Return "title – artist" (or the title alone). */
function labelOf(item) {
  return item.artist ? `${item.title} – ${item.artist}` : item.title;
}
