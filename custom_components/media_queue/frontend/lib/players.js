// Which media players the panel offers, and what they can do.

export const FEATURE = {
  PAUSE: 1,
  VOLUME_SET: 4,
  PLAY_MEDIA: 512,
  PLAY: 16384,
  BROWSE_MEDIA: 131072,
};

/** Return whether a state object's supported_features include feature. */
export function supports(stateObj, feature) {
  return ((stateObj?.attributes?.supported_features ?? 0) & feature) !== 0;
}

/** Return the players that can play media, sorted by name. */
export function listPlayers(states) {
  return Object.values(states ?? {})
    .filter((s) => s.entity_id.startsWith("media_player.") && supports(s, FEATURE.PLAY_MEDIA))
    .map((s) => ({
      entityId: s.entity_id,
      name: s.attributes.friendly_name || s.entity_id,
      canBrowse: supports(s, FEATURE.BROWSE_MEDIA),
    }))
    .sort((a, b) => a.name.localeCompare(b.name) || a.entityId.localeCompare(b.entityId));
}

/** Return a short text that changes only when the player list changes. */
export function playersKey(players) {
  return players.map((p) => `${p.entityId}|${p.name}|${p.canBrowse}`).join(";");
}
