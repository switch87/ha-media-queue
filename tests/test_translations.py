"""Tests for the translation files."""

import json
from pathlib import Path
import re
from typing import Any

from homeassistant.util.yaml import load_yaml_dict

COMPONENT = Path(__file__).parent.parent / "custom_components" / "media_queue"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
    return data


def _strings(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    strings: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            strings |= _strings(value, path)
        else:
            strings[path] = value
    return strings


def test_english_matches_strings() -> None:
    """translations/en.json is a copy of strings.json."""
    assert _load("translations/en.json") == _load("strings.json")


def test_dutch_is_complete() -> None:
    """Every string has a Dutch translation with the same placeholders."""
    english = _strings(_load("strings.json"))
    dutch = _strings(_load("translations/nl.json"))
    assert dutch.keys() == english.keys()
    for key, text in english.items():
        assert set(re.findall(r"\{\w+\}", dutch[key])) == set(
            re.findall(r"\{\w+\}", text)
        ), key


def test_every_exception_key_is_translated() -> None:
    """Each translation_key raised in the code has a message."""
    used = {
        key
        for source in COMPONENT.glob("*.py")
        for key in re.findall(
            r'(?:translation_key=|_invalid\()"([a-z_]+)"',
            source.read_text(encoding="utf-8"),
        )
    }
    assert used == set(_load("strings.json")["exceptions"])
    assert len(used) >= 9  # the regex really finds them


def test_every_service_and_field_is_described() -> None:
    """services.yaml and the strings describe the same actions and fields."""
    services = load_yaml_dict(COMPONENT / "services.yaml")
    strings = _load("strings.json")["services"]
    assert set(services) == set(strings)
    for name, service in services.items():
        assert set(service["fields"]) == set(strings[name]["fields"]), name


def test_no_references_in_translations() -> None:
    """Custom integrations get no [%key:…] resolution: every text is written out."""
    for path in (COMPONENT / "translations").glob("*.json"):
        assert "[%key:" not in path.read_text(encoding="utf-8"), path.name


def test_every_service_has_an_icon() -> None:
    """icons.json has an icon for every action (hassfest checks this too)."""
    services = load_yaml_dict(COMPONENT / "services.yaml")
    assert set(_load("icons.json")["services"]) == set(services)


def test_manifest_keys_in_hassfest_order() -> None:
    """domain and name first, then the other keys alphabetically."""
    keys = list(_load("manifest.json"))
    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])
