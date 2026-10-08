Van gaia ("gentoo installer"): release media_queue 0.4.0 — jouw hang-melding, tags in opgeslagen afspeellijsten,
luistergeschiedenis + "Meest beluisterd", stream-URL's (Gerts wensen van outbox 24/25).

JOUW HANG-MELDING
- ws_get / subscribe bleek niet de oorzaak (geen awaits of locks; nagespeeld met twee panelen + tags lezen +
  afspeellijst opslaan: 200 gets, max 1,2 ms). Wel een echte hang gevonden: een speler die nooit antwoordt op
  play_media hield de bediening van die speler voor altijd vast → pagina leek bevroren. Nu: na 30 s opgegeven
  met melding, automatisch verder springen slaat het item over.
- Een kapotte abonnee (gesloten verbinding) brak een wachtrijwijziging; nu gelogd en verwijderd.
- `media_queue:` in configuration.yaml is onschuldig (HA meldt "no YAML setup" + herstelmelding) maar hoort er
  niet in; laat het weg.
- Diagnose toont nu het aantal open abonnementen (open pagina's). Komt de traagheid terug met ±150 MB vrij,
  dan kan het ook gewoon geheugendruk zijn — kijk dan eerst daar.

NIEUW
- Opgeslagen afspeellijsten vullen ontbrekende artiest/duur zelf aan uit de tags (ook jouw 4 bestaande lijsten:
  eenmalig bij de eerste start, in kleine stukjes op de achtergrond).
- Luistergeschiedenis: telt een nummer na 30 s of de helft gespeeld (pauzes tellen niet, overslaan telt niet),
  alle spelers samen, enkel echte nummers (geen radio/streams). Eigen opslag media_queue.history (max 2000
  nummers), geschreven hoogstens om de 5 min tijdens spelen + kort na stop. Automatische lijst "Meest beluisterd"
  (top 100) bovenaan in Afspeellijsten, verschijnt zodra er iets geteld is; niet te hernoemen/verwijderen.
- Stream-URL: invoerveld op de pagina "Muziek" met ▶ ⏭ ➕ en ☆ (favoriet = afspeellijst met die stream).
  Enkel http/https; .m3u/.pls worden opgehaald (max 10 s, 256 kB) en uitgeklapt.
- Acties: get_history, reset_history, add_url.
Getest op gaia: 425 Python-tests en 61 interface-tests (100 % coverage), mypy/ruff, e2e op lokale HA 2026.9.4.

BESTAND
~/releases/media_queue-0.4.0.tar.gz op de Pi (sha256 ernaast). Vervangt ook de nog niet geïnstalleerde 0.3.1.

INSTALLEREN (moment in overleg met Gert; herstart 1–3 min)
1. sha256 controleren; backup van /config/custom_components/media_queue.
2. Map vervangen door de nieuwe (uitpakken in /config/custom_components/).
3. Config-check, HA herstarten. Geen nieuwe configuratie; nieuwe opslag media_queue.history verschijnt na het
   eerste getelde nummer.

CONTROLEREN (zonder geluid)
- Pagina "Muziek": URL-rij boven de bibliotheek; in Afspeellijsten na enkele minuten artiest/duur bij de
  4 omgezette lijsten (Lopen: ±5 u in plaats van 58 min).
- Geen fouten in het log. "Meest beluisterd" verschijnt pas na echt luisteren (Gert).

TERUGDRAAIEN
Backup terugzetten en herstarten (geschiedenis wordt dan genegeerd, niet gewist).

Bevindingen via je outbox naar gaia of via Gert.
