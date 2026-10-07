// Labels of the panel in English and Dutch, chosen by the user's HA language.

export const STRINGS = {
  en: {
    title: "Music",
    player: "Player",
    no_players: "No media players that can play media.",
    library: "Library",
    queue: "Queue",
    back: "Back",
    loading: "Loading…",
    empty_folder: "Nothing here.",
    cannot_browse: "This player cannot browse; showing all media sources.",
    play: "Play",
    play_next: "Play next",
    add: "Add to queue",
    open: "Open",
    clear: "Clear queue",
    empty_queue: "The queue is empty. Add tracks, albums or folders from the library.",
    items: "{count} items",
    remove: "Remove",
    move: "Drag to move",
    previous: "Previous",
    next: "Next",
    play_pause: "Play/pause",
    volume: "Volume",
    nothing_playing: "Nothing is playing",
    added: "{count} added to the queue.",
    truncated: "Only the first {limit} items were added.",
    error: "Error: {message}",
  },
  nl: {
    title: "Muziek",
    player: "Speler",
    no_players: "Geen mediaspelers die media kunnen afspelen.",
    library: "Bibliotheek",
    queue: "Wachtrij",
    back: "Terug",
    loading: "Laden…",
    empty_folder: "Hier staat niets.",
    cannot_browse: "Deze speler kan niet bladeren; alle mediabronnen worden getoond.",
    play: "Afspelen",
    play_next: "Hierna afspelen",
    add: "Aan wachtrij toevoegen",
    open: "Openen",
    clear: "Wachtrij leegmaken",
    empty_queue: "De wachtrij is leeg. Voeg nummers, albums of mappen toe uit de bibliotheek.",
    items: "{count} items",
    remove: "Verwijderen",
    move: "Sleep om te verplaatsen",
    previous: "Vorige",
    next: "Volgende",
    play_pause: "Afspelen/pauzeren",
    volume: "Volume",
    nothing_playing: "Er speelt niets",
    added: "{count} toegevoegd aan de wachtrij.",
    truncated: "Alleen de eerste {limit} items zijn toegevoegd.",
    error: "Fout: {message}",
  },
};

/** Return "nl" for Dutch users, "en" for everyone else. */
export function languageOf(hass) {
  const language = hass?.locale?.language ?? hass?.language ?? "en";
  return language.toLowerCase().startsWith("nl") ? "nl" : "en";
}

/** Return the label for key in language, with {placeholders} filled. */
export function translate(language, key, params = {}) {
  const text = STRINGS[language]?.[key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (hole, name) => (name in params ? String(params[name]) : hole));
}
