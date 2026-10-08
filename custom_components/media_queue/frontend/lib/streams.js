// Stream URLs typed in the library column: checking them, naming them, messages.

const URL_MAX = 2000;
const WEB_URL = /^https?:\/\/[^/\s?#]+/i;

/** Return the trimmed http(s) URL with a host, or null (the server checks again). */
export function cleanUrl(text) {
  const url = (text ?? "").trim();
  if (!url || url.length > URL_MAX || /\s/.test(url) || !WEB_URL.test(url)) {
    return null;
  }
  return url;
}

/** Return a name for a URL: its last path part, else its host. */
export function suggestName(url) {
  const { hostname, pathname } = new URL(url);
  const last = pathname.replace(/\/+$/, "").split("/").pop();
  if (!last) {
    return hostname;
  }
  try {
    return decodeURIComponent(last);
  } catch {
    return last;
  }
}

/** Return the message that adds a stream URL to a player's queue in mode. */
export const addUrlMessage = (entityId, url, mode) => ({
  type: "media_queue/add_url",
  entity_id: entityId,
  url,
  mode,
});

/** Return the message that saves a stream URL as a favourite (a playlist). */
export const saveStreamMessage = (url, name, overwrite) => ({
  type: "media_queue/streams/save",
  url,
  name,
  overwrite,
});
