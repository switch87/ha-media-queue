Van gaia ("gentoo installer"): release media_queue 0.2.0 — shuffle, herhalen en titels uit de tags (Gerts wensen van outbox 21).

NIEUW
- SHUFFLE-knop bovenaan (per speler): de wachtrij toont meteen de echte afspeelvolgorde; het nummer dat
  speelt blijft spelen en staat bovenaan. Shuffle uit = oorspronkelijke volgorde terug. Nieuwe nummers
  tijdens shuffle: "toevoegen" mengt ze willekeurig erna, "hierna"/"afspelen" komen direct na het huidige.
- HERHALEN-knop (cyclus uit → alles → één nummer): "alles" begint na het laatste nummer opnieuw (met
  shuffle opnieuw geschud), "één" speelt het huidige opnieuw; volgende/vorige werken gewoon.
- Stand van shuffle/herhalen per speler bewaard, ook na een herstart. MPD's eigen repeat/random blijven
  uit (HA regelt het).
- Wachtrij toont "titel – artiest" uit de tags (ID3/FLAC/…); bestandsnaam staat in de tooltip. Nummers
  verschijnen meteen, de tags worden daarna in kleine stukjes ingelezen. Albumhoezen in de bestanden worden
  NIET ingelezen (alleen enkele kB per bestand). Bij een hangende NAS stopt het tags lezen 10 min voor die
  speler.
- Knoppen werken ook met het toetsenbord (focus blijft staan).
Getest op gaia: 284 Python-tests en 47 interface-tests (100 % coverage), mypy/ruff, twee reviews, e2e op
lokale HA 2026.9.4. Afspelen op de echte speakers test Gert.

BESTAND
~/releases/media_queue-0.2.0.tar.gz op de Pi (sha256 in ~/releases/media_queue-0.2.0.tar.gz.sha256).

INSTALLEREN (moment in overleg met Gert; herstart 1–3 min)
1. sha256 controleren; backup van /config/custom_components/media_queue (0.1.0).
2. Map /config/custom_components/media_queue vervangen door de nieuwe (uitpakken in /config/custom_components/).
3. Config-check, HA herstarten. Geen nieuwe configuratie nodig; de bestaande wachtrijen worden automatisch
   omgezet (opslag 1.1 → 1.2). mutagen (tags) zit al in HA (tts), anders installeert HA het bij de start.
4. Browser herladen op de pagina "Muziek" (nieuwe versie wordt automatisch opgehaald).

CONTROLEREN (zonder geluid)
- Shuffle- en herhalen-knop staan bovenaan bij de bediening; een album toevoegen toont na enkele seconden
  titels/artiesten i.p.v. bestandsnamen; shuffle aan/uit herschikt de wachtrij zonder iets af te spelen.
- Geen fouten in het log.
- Voor Gert bij het eerste gebruik: herhalen "één nummer" eens proberen op Werkplaats én Living Room
  (alleen op demo-spelers getest).

TERUGDRAAIEN
Backup van 0.1.0 terugzetten en herstarten (0.1.0 kan de nieuwe opslag lezen; shuffle/herhalen worden dan
genegeerd).

Bevindingen graag via je outbox naar gaia of via Gert.
