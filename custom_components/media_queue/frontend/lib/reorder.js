// Index math for dragging queue rows.

/**
 * Return the index the dragged row moves to when dropped on row `over`
 * (in its upper half when `before`), or null when nothing changes.
 */
export function dropIndex(from, over, before, count) {
  if (from < 0 || from >= count || over < 0 || over >= count) {
    return null;
  }
  const slot = before ? over : over + 1;
  const to = slot > from ? slot - 1 : slot;
  return to === from ? null : to;
}

/** Return the row under a vertical position, from row boxes {top, bottom}. */
export function rowAt(boxes, y) {
  if (!boxes.length) {
    return null;
  }
  for (let index = 0; index < boxes.length; index += 1) {
    const box = boxes[index];
    if (y < box.bottom) {
      return { index, before: y < (box.top + box.bottom) / 2 };
    }
  }
  return { index: boxes.length - 1, before: false };
}
