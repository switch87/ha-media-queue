// Remember the chosen player per browser (localStorage may be missing or fail).

export const STORAGE_KEY = "media_queue.player";

/** Store the chosen player; storage errors are ignored. */
export function rememberPlayer(storage, entityId) {
  try {
    storage?.setItem(STORAGE_KEY, entityId);
  } catch {
    // private mode or blocked storage: the choice is simply not remembered
  }
}

/** Return the remembered player if it still exists, else the first player. */
export function restorePlayer(storage, players) {
  let saved = null;
  try {
    saved = storage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    saved = null;
  }
  if (players.some((p) => p.entityId === saved)) {
    return saved;
  }
  return players.length ? players[0].entityId : null;
}
