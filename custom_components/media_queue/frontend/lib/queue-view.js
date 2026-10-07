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

/** Return a short key per row list, so the DOM is rebuilt only on changes. */
export function rowsKey(rows) {
  return rows.map((r) => `${r.id}:${r.current ? "c" : ""}${r.next ? "n" : ""}`).join(",");
}

/** Return the item playing (or last played) from the queue, if any. */
export function currentItem(snapshot) {
  const index = snapshot?.current;
  return index === null || index === undefined ? null : snapshot.items[index] ?? null;
}
