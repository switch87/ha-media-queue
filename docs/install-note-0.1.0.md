Van gaia ("gentoo installer"): release media_queue 0.1.0 — de pagina "Muziek" (vervangt music_library).

WAT
Integratie `media_queue` + zijbalkpagina "Muziek" (icoon playlist-music). Met de GEWONE spelers
(Living Room, Werkplaats, …) en ALLE bronnen uit HA's mediabrowser:
- links de bibliotheek (zelfde boom als HA's mediamenu), per item ▶ Afspelen / ⏭ Speel hierna /
  ➕ Toevoegen — ook mappen, albums, artiesten en .m3u/.pls-afspeellijsten (uitgeklapt, met titels);
  knoppen alleen bij audio (niet bij camera/afbeelding/TTS);
- rechts de wachtrij die HA zelf per speler bijhoudt: huidig nummer gemarkeerd, klik = springen,
  ✕ = verwijderen, slepen = verschuiven, leegmaken; blijft bewaard na een herstart;
- bovenaan bediening (play/pauze, vorige/volgende via de wachtrij, volume) + wat er speelt.
HA start zelf het volgende nummer als het vorige gedaan is. Radio of items zonder lengte gaan
bewust NIET vanzelf verder (Gerts keuze): een stop elders start dus nooit ongevraagd muziek.
Licht: geen achtergrondproces, geen indexering, mappen pas gelezen als je ze opent; kleine
updates naar de pagina, de wachtrij wordt pas na wijzigingen bewaard (spaart de SD-kaart).
Getest op gaia: 194 Python-tests (100 % line+branch), 34 interface-tests (100 %), mypy/ruff, twee
onafhankelijke reviews, end-to-end 30/30 op een lokale HA 2026.9.4 (geen afspeeltests op de echte
speakers, zoals Gert wil).

BESTAND
~/releases/media_queue-0.1.0.tar.gz op de Pi (door gaia met scp gezet, niet in /config),
sha256 in ~/releases/media_queue-0.1.0.tar.gz.sha256.

INSTALLEREN (op een moment dat Gert goed vindt; herstart 1–3 min)
1. sha256 controleren.
2. Oude music_library weg: /config/custom_components/music_library verwijderen (entries had je al
   verwijderd).
3. Uitpakken naar /config/custom_components/ (geeft media_queue/).
4. Config-check: docker exec homeassistant python3 -m homeassistant --script check_config -c /config
5. HA herstarten.
6. Instellingen → Apparaten & diensten → Integratie toevoegen → "Media queue" (één keer, geen
   vragen). De pagina "Muziek" verschijnt in de zijbalk (browser eventueel herladen).
7. Werkplaats/MPD: zet "herhalen" (repeat) UIT op MPD (`mpc -h 127.0.0.1 repeat off` op de router),
   anders blijft MPD het eerste nummer herhalen en gaat de wachtrij nooit verder.

GOED OM TE WETEN
- HA's eigen mpd-integratie wist bij elk nummer MPD's eigen afspeellijst — de wachtrij leeft nu in
  HA, dus dat is de bedoeling.
- Sonos: muziek van de NAS gaat via een URL van HA zelf (lokale mediabron). De Sonos moet HA dus
  kunnen bereiken op zijn interne URL (Instellingen → Systeem → Netwerk). Sonos-favorieten en de
  Sonos-bibliotheek vervangen Sonos' eigen wachtrij (staat als opmerking op de pagina).
- Als een nummer niet start (speler onbereikbaar, formaat niet ondersteund), slaat HA het na ±25 s
  over (max 3 keer na elkaar) en toont de pagina een melding.

CONTROLEREN (zonder geluid)
- Pagina "Muziek" opent; spelerkeuze toont Living Room en Werkplaats; bibliotheek → My media →
  muziek → een artiest toont ▶/⏭/➕; een album met ➕ toevoegen zet het in de wachtrij zonder af te spelen.
  Geen fouten in het log.
- Echt afspelen: Gert.

TERUGDRAAIEN
Integratie verwijderen (wist ook de bewaarde wachtrijen), map /config/custom_components/media_queue
weg, HA herstarten.

Meld bevindingen aan mij via ~/agents-bus/gaia/inbox op gaia of via Gert; fouten los ik hier op en
lever ik als nieuwe versie — niets op de Pi aanpassen.
