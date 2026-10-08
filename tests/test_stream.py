"""Tests for stream URLs: validation and .m3u/.pls expansion over HTTP."""

import asyncio
from unittest.mock import patch

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.media_queue import stream as stream_module
from custom_components.media_queue.stream import async_expand_url, check_url

M3U = "http://radio.example/list.m3u"


def _key(err: pytest.ExceptionInfo[ServiceValidationError]) -> str | None:
    return err.value.translation_key


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "media-source://media_source/local/a.mp3",
        "ftp://radio.example/a.mp3",
        "javascript:alert(1)",
        "http://",
        "radio.example/stream",
        "",
        "http://radio.example/" + "x" * 2100,
        "http://radio.example/a b",
    ],
)
def test_only_http_and_https_urls(url: str) -> None:
    """Everything but a plain http(s) URL with a host is refused."""
    with pytest.raises(ServiceValidationError) as err:
        check_url(url)
    assert _key(err) == "invalid_url"


def test_a_url_is_trimmed() -> None:
    """Spaces around a pasted URL are dropped."""
    assert check_url("  HTTPS://radio.example/live  ") == "HTTPS://radio.example/live"


async def test_a_plain_stream_is_one_item_without_a_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A stream URL is not fetched: nothing is downloaded or probed."""
    expansion = await async_expand_url(
        hass, "http://radio.example/live/stream%20one.mp3", None, limit=10
    )
    assert aioclient_mock.call_count == 0
    (item,) = expansion.items
    assert item.media_content_id == "http://radio.example/live/stream%20one.mp3"
    assert item.media_content_type == "music"
    assert item.title == "stream one.mp3"
    assert item.media_class == "music"
    assert item.duration is None

    named = await async_expand_url(hass, "https://radio.example/", "My radio", limit=1)
    assert named.items[0].title == "My radio"
    bare = await async_expand_url(hass, "https://radio.example", None, limit=1)
    assert bare.items[0].title == "radio.example"


async def test_an_m3u_is_expanded(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Entries become items, relative ones resolved against the playlist."""
    aioclient_mock.get(
        M3U,
        text=(
            "#EXTM3U\n#EXTINF:-1,Radio One\nhttp://one.example/live\n"
            "relative/two.mp3\nfile:///etc/passwd\n/abs.aac\n"
        ),
        headers={"Content-Type": "audio/x-mpegurl; charset=utf-8"},
    )
    expansion = await async_expand_url(hass, M3U, None, limit=10)
    assert [(i.media_content_id, i.title) for i in expansion.items] == [
        ("http://one.example/live", "Radio One"),
        ("http://radio.example/relative/two.mp3", "two.mp3"),
        ("http://radio.example/abs.aac", "abs.aac"),
    ]
    assert not expansion.truncated


async def test_a_pls_is_expanded_and_capped(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A .pls with titles; the limit cuts it off."""
    url = "https://radio.example/STREAM.PLS"
    aioclient_mock.get(
        url,
        content="[playlist]\nFile1=http://a.example/1\nTitle1=First\n"
        "File2=http://a.example/2\nNumberOfEntries=2\n".encode("latin-1"),
        headers={"Content-Type": "audio/x-scpls"},
    )
    expansion = await async_expand_url(hass, url, None, limit=1)
    assert [(i.media_content_id, i.title) for i in expansion.items] == [
        ("http://a.example/1", "First")
    ]
    assert expansion.truncated


@pytest.mark.parametrize("content_type", ["text/plain", "application/octet-stream"])
async def test_servers_that_do_not_say_playlist(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, content_type: str
) -> None:
    """Many servers send playlists as plain text or bytes; that is fine."""
    aioclient_mock.get(
        M3U,
        content=b"\xef\xbb\xbfhttp://one.example/caf\xc3\xa9",
        headers={"Content-Type": content_type},
    )
    expansion = await async_expand_url(hass, M3U, None, limit=10)
    assert expansion.items[0].media_content_id == "http://one.example/café"


async def test_latin1_playlists(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A playlist that is no UTF-8 is read as Latin-1."""
    aioclient_mock.get(
        M3U, content="#EXTINF:1,Caf\xe9\nhttp://a.example/x\n".encode("latin-1")
    )
    expansion = await async_expand_url(hass, M3U, None, limit=10)
    assert expansion.items[0].title == "Café"


async def test_a_big_playlist_is_read_only_partly(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Never more than MAX_PLAYLIST_BYTES are read."""
    aioclient_mock.get(M3U, text="http://a.example/1\n" + "#" * 100 + "\nhttp://b/2\n")
    with patch.object(stream_module, "MAX_PLAYLIST_BYTES", 20):
        expansion = await async_expand_url(hass, M3U, None, limit=10)
    assert [i.media_content_id for i in expansion.items] == ["http://a.example/1"]


@pytest.mark.parametrize("content_type", ["text/html", "audio/mpeg", "image/png"])
async def test_wrong_content_is_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, content_type: str
) -> None:
    """An error page or an audio stream behind a .m3u name is no playlist."""
    aioclient_mock.get(
        M3U, text="<html>http://x</html>", headers={"Content-Type": content_type}
    )
    with pytest.raises(ServiceValidationError) as err:
        await async_expand_url(hass, M3U, None, limit=10)
    assert _key(err) == "stream_bad_content"
    assert err.value.translation_placeholders == {
        "url": M3U,
        "content_type": content_type,
    }


async def test_an_empty_playlist_is_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A playlist without http(s) entries gives a clear message."""
    aioclient_mock.get(M3U, text="#EXTM3U\nfile:///x.mp3\n")
    with pytest.raises(ServiceValidationError) as err:
        await async_expand_url(hass, M3U, None, limit=10)
    assert _key(err) == "stream_empty"


@pytest.mark.parametrize(
    "failure",
    [
        {"status": 404},
        {"exc": ClientError()},
        {"exc": TimeoutError()},
    ],
)
async def test_unreachable_playlists(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, failure: dict[str, object]
) -> None:
    """HTTP errors, connection errors and timeouts: one translated message."""
    aioclient_mock.get(M3U, **failure)
    with pytest.raises(ServiceValidationError) as err:
        await async_expand_url(hass, M3U, None, limit=10)
    assert _key(err) == "stream_unreachable"
    assert err.value.translation_placeholders == {"url": M3U}


async def test_a_slow_server_times_out(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A server that never answers is given up after STREAM_TIMEOUT."""

    async def never(*args: object) -> None:
        await asyncio.sleep(3600)

    aioclient_mock.get(M3U, side_effect=never)
    with (
        patch.object(stream_module, "STREAM_TIMEOUT", 0.05),
        pytest.raises(ServiceValidationError) as err,
    ):
        await async_expand_url(hass, M3U, None, limit=10)
    assert _key(err) == "stream_unreachable"
