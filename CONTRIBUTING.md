# Contributing

Thanks for helping. Bug reports, ideas and pull requests are welcome at
<https://github.com/switch87/ha-media-queue/issues>.

## Reporting a bug

Please include:

- the Home Assistant version and the version of Media queue,
- the player integration involved (MPD, Sonos, …) and the media source,
- what you did, what you expected and what happened,
- the diagnostics (*Devices & services → Media queue → ⋮ → Download
  diagnostics*) and relevant log lines; for more detail add
  ```yaml
  logger:
    logs:
      custom_components.media_queue: debug
  ```

## Development setup

Python 3.14 and Node.js 24 (or newer).

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
```

`requirements_test.txt` pins `pytest-homeassistant-custom-component` to the
Home Assistant version the integration is tested against.

## Checks (all must pass, CI runs the same)

```bash
.venv/bin/python -m pytest -q                       # 100 % line and branch coverage, enforced
.venv/bin/mypy custom_components tests scripts      # --strict (mypy.ini)
.venv/bin/ruff check . && .venv/bin/ruff format --check .
npm test                                            # node --test, 100 % for frontend/lib
```

- **Python**: coverage is part of the pytest run (`pytest.ini`); a change that
  leaves a line or branch untested fails. No `# pragma: no cover`.
- **Frontend**: the panel (`frontend/media-queue-panel.js`) is a thin DOM
  layer without a build step; all logic lives in `frontend/lib/*.js` and is
  tested with Node's built-in test runner at 100 % lines, branches and
  functions (no npm packages needed).
- **Test first**: write a test that fails on an assertion about the missing
  behaviour, then the code.
- Strings: English in `strings.json` and `translations/en.json` (identical),
  Dutch in `translations/nl.json`; the panel's labels are in
  `frontend/lib/i18n.js`. Tests check that both languages are complete.

## Trying it in a real Home Assistant

Run a throwaway Home Assistant in its own virtual environment with the
`demo` integration (demo media players) and a local media folder, and link
the component into its configuration:

```bash
python3.14 -m venv ~/ha-dev/venv && ~/ha-dev/venv/bin/pip install homeassistant
mkdir -p ~/ha-dev/config/custom_components
ln -s "$PWD/custom_components/media_queue" ~/ha-dev/config/custom_components/
python scripts/make_dev_library.py ~/ha-dev/lib   # tiny tagged MP3 albums
```

with in `~/ha-dev/config/configuration.yaml`:

```yaml
homeassistant:
  media_dirs:
    local: /home/<you>/ha-dev/lib
default_config:
demo:
```

and start it with `~/ha-dev/venv/bin/hass -c ~/ha-dev/config`.

## Pull requests

- One topic per pull request, with tests; keep commits focused.
- Describe the behaviour change and how you checked it (screenshots for
  panel changes help).
- By contributing you agree that your contribution is licensed under the MIT
  licence of this project.
