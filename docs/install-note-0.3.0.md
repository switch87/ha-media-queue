Van gaia ("gentoo installer"): release media_queue 0.3.0 — afspeellijsten (Gerts wens: "een wachtrij als playlist
opslaan, in een lokale library van playlists die voor alle players beschikbaar is").

NIEUW
- Pagina "Muziek": knop 💾 boven de wachtrij = wachtrij opslaan als afspeellijst (naam geven; bestaande naam →
  eerst vragen of overschrijven). Opgeslagen in de geschudde volgorde als shuffle aan staat.
- Bovenaan de bibliotheek een map "Afspeellijsten" voor ELKE speler: ▶ / ⏭ / ➕ zoals de rest, openen (nummers
  met eigen knoppen), hernoemen, verwijderen (met bevestiging). Nummers uit alle bronnen (NAS, DLNA, radio).
- In HA's gewone mediabrowser een bron "Afspeellijsten (Muziek)": lijst openen en één nummer afspelen; een hele
  lijst laden gaat via de pagina "Muziek" of de actie media_queue.load_playlist.
- Acties save_playlist / load_playlist / rename_playlist / delete_playlist / get_playlists.
- Zijbalknaam volgt de taal van HA ("Muziek" bij Nederlands, zoals nu).
Getest op gaia: 326 Python-tests en 55 interface-tests (100 % coverage), mypy/ruff, e2e op lokale HA 2026.9.4
(opslaan op speler A, laden op speler B met elke knop, hernoemen, verwijderen, HA-mediabrowser). Afspelen op de
echte speakers test Gert.

BESTAND
~/releases/media_queue-0.3.0.tar.gz op de Pi (sha256 in ~/releases/media_queue-0.3.0.tar.gz.sha256).

INSTALLEREN (moment in overleg met Gert; herstart 1–3 min)
1. sha256 controleren; backup van /config/custom_components/media_queue (0.2.0).
2. Map /config/custom_components/media_queue vervangen door de nieuwe (uitpakken in /config/custom_components/).
3. Config-check, HA herstarten. Geen nieuwe configuratie; bij de start verschijnt .storage/media_queue.playlists
   (pas na de eerste opgeslagen lijst). Bestaande wachtrijen blijven.
4. Browser herladen op de pagina "Muziek".

CONTROLEREN (zonder geluid)
- Knop 💾 boven de wachtrij; map "Afspeellijsten" bovenaan de bibliotheek ("nog geen opgeslagen afspeellijsten").
- Media in de zijbalk toont de bron "Afspeellijsten (Muziek)".
- Geen fouten in het log.

TERUGDRAAIEN
Backup van 0.2.0 terugzetten en herstarten (opgeslagen afspeellijsten worden dan genegeerd, niet gewist).

Bevindingen graag via je outbox naar gaia of via Gert.
