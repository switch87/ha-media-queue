// Transport buttons: what play/pause, previous, next and volume do.

import { FEATURE, supports } from "./players.js";
import { currentItem } from "./queue-view.js";

/**
 * Return what the play/pause button does:
 * {kind: "service", service} on the player itself, {kind: "queue", index} to
 * start the queue, or null when there is nothing to play.
 */
export function playPauseAction(stateObj, snapshot) {
  const state = stateObj?.state;
  if (state === "playing") {
    return {
      kind: "service",
      service: supports(stateObj, FEATURE.PAUSE) ? "media_pause" : "media_stop",
      icon: "mdi:pause",
    };
  }
  if (state === "paused" && supports(stateObj, FEATURE.PLAY)) {
    return { kind: "service", service: "media_play", icon: "mdi:play" };
  }
  const items = snapshot?.items ?? [];
  if (!items.length) {
    return null;
  }
  const index = snapshot.current ?? snapshot.next ?? 0;
  return { kind: "queue", index, icon: "mdi:play" };
}

/** Return whether previous/next through the queue make sense now. */
export function queueButtons(snapshot) {
  const count = snapshot?.items?.length ?? 0;
  const hasNext = snapshot?.next !== null && snapshot?.next !== undefined;
  return { previous: count > 0, next: hasNext || (snapshot?.repeat === "all" && count > 0) };
}

/** Return the volume (0–100) when the player can set it, else null. */
export function volumeOf(stateObj) {
  if (!supports(stateObj, FEATURE.VOLUME_SET)) {
    return null;
  }
  const level = stateObj.attributes.volume_level;
  return typeof level === "number" ? Math.round(level * 100) : 0;
}

/** Return title, subtitle and picture for the now-playing bar. */
export function nowPlaying(stateObj, snapshot) {
  const attrs = stateObj?.attributes ?? {};
  const active = ["playing", "paused", "buffering"].includes(stateObj?.state);
  const item = currentItem(snapshot);
  const title = (active && attrs.media_title) || item?.title || null;
  const parts = active ? [attrs.media_artist, attrs.media_album_name] : [item?.artist, item?.album];
  const subtitle = parts.filter(Boolean).join(" – ");
  return {
    title,
    subtitle,
    picture: (active && attrs.entity_picture) || item?.thumbnail || null,
  };
}

/** Return the shuffle toggle: state, icon, title key and the value a click sends. */
export function shuffleButton(snapshot) {
  const on = snapshot?.shuffle === true;
  return {
    pressed: on,
    icon: on ? "mdi:shuffle-variant" : "mdi:shuffle-disabled",
    title: on ? "shuffle_on" : "shuffle_off",
    value: !on,
  };
}

const REPEAT = {
  off: { icon: "mdi:repeat-off", next: "all" },
  all: { icon: "mdi:repeat", next: "one" },
  one: { icon: "mdi:repeat-once", next: "off" },
};

/**
 * Return the repeat button; a click cycles off → all → one → off. It has three
 * states, so it is no toggle: its name (title key) says the state.
 */
export function repeatButton(snapshot) {
  const mode = REPEAT[snapshot?.repeat] ? snapshot.repeat : "off";
  return {
    icon: REPEAT[mode].icon,
    title: `repeat_${mode}`,
    value: REPEAT[mode].next,
    active: mode !== "off", // looks highlighted; not announced as "pressed"
  };
}
