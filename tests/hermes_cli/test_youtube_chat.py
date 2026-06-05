from unittest.mock import patch


def test_extract_youtube_video_id_accepts_common_urls():
    from hermes_cli.youtube_chat import extract_youtube_video_id

    assert extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("not a video") == ""


def test_load_youtube_chat_config_is_shape_safe():
    from hermes_cli.youtube_chat import load_youtube_chat_config

    cfg = load_youtube_chat_config(
        {
            "youtube_chat": {
                "enabled": "true",
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "poll_interval_seconds": "0",
                "max_results": 500,
                "selection": {
                    "blocked_terms": ["NG"],
                    "spoiler_terms": ["ラスボス"],
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.video_id == "dQw4w9WgXcQ"
    assert cfg.poll_interval_seconds == 5.0
    assert cfg.max_results == 50
    assert cfg.blocked_terms == ("NG",)
    assert cfg.spoiler_terms == ("ラスボス",)
    assert cfg.backend == "innertube"


def test_resolve_live_chat_id_uses_videos_api():
    from hermes_cli.youtube_chat import resolve_live_chat_id

    def fake_get(path, *, api_key, params, timeout):
        assert path == "videos"
        assert api_key == "key"
        assert params == {"part": "liveStreamingDetails", "id": "dQw4w9WgXcQ"}
        assert timeout == 3
        return {"items": [{"liveStreamingDetails": {"activeLiveChatId": "chat-1"}}]}

    with patch("hermes_cli.youtube_chat._youtube_get", side_effect=fake_get):
        assert resolve_live_chat_id(video_id="dQw4w9WgXcQ", api_key="key", timeout_seconds=3) == "chat-1"


def test_fetch_youtube_chat_messages_classifies_spoilers_and_selection():
    from hermes_cli.youtube_chat import YouTubeChatConfig, fetch_youtube_chat_messages

    def fake_get(path, *, api_key, params, timeout):
        assert path == "liveChat/messages"
        assert params["liveChatId"] == "chat-1"
        return {
            "nextPageToken": "next",
            "pollingIntervalMillis": 9000,
            "items": [
                {
                    "id": "m1",
                    "snippet": {"displayMessage": "こんにちは", "publishedAt": "2026-06-02T00:00:00Z"},
                    "authorDetails": {"displayName": "viewer"},
                },
                {
                    "id": "m2",
                    "snippet": {"displayMessage": "ネタバレです"},
                    "authorDetails": {"displayName": "viewer2"},
                },
            ],
        }

    cfg = YouTubeChatConfig(poll_interval_seconds=5.0)
    with patch("hermes_cli.youtube_chat._youtube_get", side_effect=fake_get):
        messages, token, interval = fetch_youtube_chat_messages(
            live_chat_id="chat-1",
            config=cfg,
            api_key="key",
        )

    assert token == "next"
    assert interval == 9.0
    assert messages[0].is_selected is True
    assert messages[0].display_text == "viewer: こんにちは"
    assert messages[1].is_selected is False
    assert messages[1].rejection_reason == "spoiler_term"


def test_parse_innertube_bridge_message_uses_same_selection():
    from hermes_cli.youtube_chat import YouTubeChatConfig, parse_innertube_bridge_message

    selected = parse_innertube_bridge_message(
        {
            "type": "message",
            "id": "m1",
            "author": "viewer",
            "text": "ここは右ですか？",
            "timestamp": "2026-06-02T00:00:00.000Z",
            "isModerator": True,
            "isMember": False,
            "authorChannelId": "UC123",
        },
        YouTubeChatConfig(),
    )
    spoiler = parse_innertube_bridge_message(
        {"type": "message", "id": "m2", "author": "viewer", "text": "ネタバレです"},
        YouTubeChatConfig(),
    )

    assert selected is not None
    assert selected.message_id == "m1"
    assert selected.author_name == "viewer"
    assert selected.is_moderator is True
    assert selected.author_channel_id == "UC123"
    assert selected.is_selected is True
    assert spoiler is not None
    assert spoiler.is_selected is False
    assert spoiler.rejection_reason == "spoiler_term"


def test_innertube_bridge_reads_ndjson_and_deduplicates(tmp_path, monkeypatch):
    from hermes_cli.youtube_chat import YouTubeChatConfig, YouTubeInnerTubeBridge

    bridge_file = tmp_path / "bridge.mjs"
    bridge_file.write_text("", encoding="utf-8")
    delivered = []

    class FakeStdout:
        def __iter__(self):
            return iter(
                [
                    '{"type":"ready"}\n',
                    '{"type":"message","id":"m1","author":"viewer","text":"hello"}\n',
                    '{"type":"message","id":"m1","author":"viewer","text":"hello again"}\n',
                    '{"type":"message","id":"m2","author":"viewer","text":"ネタバレ"}\n',
                ]
            )

    class FakeProc:
        stdout = FakeStdout()
        stderr = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    cfg = YouTubeChatConfig(
        video_id="dQw4w9WgXcQ",
        bridge_path=str(bridge_file),
        node_path="node-test",
    )
    bridge = YouTubeInnerTubeBridge(cfg, on_message=delivered.append)
    bridge.start()
    bridge._thread.join(timeout=2)

    assert captured["args"] == ["node-test", str(bridge_file), "--video-id", "dQw4w9WgXcQ"]
    assert [m.message_id for m in bridge.drain()] == ["m1"]
    assert [m.message_id for m in delivered] == ["m1"]


def test_create_youtube_chat_reader_selects_backend():
    from hermes_cli.youtube_chat import (
        YouTubeChatConfig,
        YouTubeInnerTubeBridge,
        YouTubeLiveChatPoller,
        create_youtube_chat_reader,
    )

    assert isinstance(
        create_youtube_chat_reader(YouTubeChatConfig(backend="innertube", video_id="dQw4w9WgXcQ")),
        YouTubeInnerTubeBridge,
    )
    assert isinstance(
        create_youtube_chat_reader(YouTubeChatConfig(backend="api", live_chat_id="chat-1")),
        YouTubeLiveChatPoller,
    )


def test_poller_deduplicates_and_skips_unselected_messages():
    from hermes_cli.youtube_chat import YouTubeChatConfig, YouTubeLiveChatPoller

    cfg = YouTubeChatConfig(live_chat_id="chat-1", selected_only=True)
    delivered = []

    def fake_fetch(*, live_chat_id, config, api_key, page_token):
        return (
            [
                config_message("m1", "hello", selected=True),
                config_message("m2", "spoiler", selected=False, reason="spoiler_term"),
            ],
            "next",
            5.0,
        )

    with patch("hermes_cli.youtube_chat.fetch_youtube_chat_messages", side_effect=fake_fetch):
        poller = YouTubeLiveChatPoller(cfg, api_key="key", on_message=delivered.append)
        fresh1 = poller.poll_once()
        fresh2 = poller.poll_once()

    assert [m.message_id for m in fresh1] == ["m1"]
    assert fresh2 == []
    assert [m.message_id for m in delivered] == ["m1"]


def test_publish_youtube_chat_to_overlay_uses_chat_lane(monkeypatch):
    from hermes_cli.youtube_chat import publish_youtube_chat_to_overlay

    calls = []
    monkeypatch.setattr(
        "hermes_cli.live_overlay.publish_caption",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True},
    )

    message = config_message("m1", "ここは右ですか？", selected=True)
    result = publish_youtube_chat_to_overlay(
        {"youtube_chat": {"overlay": {"ttl_seconds": 15}}},
        message,
    )

    assert result == {"ok": True}
    assert calls[0][0][1] == "viewer: ここは右ですか？"
    assert calls[0][1]["speaker"] == "chat"
    assert calls[0][1]["ttl_seconds"] == 15.0


def config_message(message_id, text, *, selected, reason=""):
    from hermes_cli.youtube_chat import YouTubeChatMessage

    return YouTubeChatMessage(
        message_id=message_id,
        author_name="viewer",
        text=text,
        is_selected=selected,
        rejection_reason=reason,
    )
