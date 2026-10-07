// What the queue list shows, from a media_queue snapshot.

/** Return the rows of the queue. */
export function queueRows(snapshot) {
  const items = snapshot?.items ?? [];
  return items.map((item, index) => ({
    index,
    id: item.id,
    title: item.title,
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

/** Return a key of the item order only (markers change in place). */
export function idsKey(rows) {
  return rows.map((r) => r.id).join(",");
}
