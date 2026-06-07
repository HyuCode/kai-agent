from hermes_cli.stream_assistant import (
    apply_stream_mode,
    format_apply_result,
    format_status,
    stream_mode_status,
)


def test_apply_stream_game_mode_writes_required_settings():
    calls = []

    def saver(key, value):
        calls.append((key, value))
        return True

    result = apply_stream_mode("game", saver=saver)

    assert result["success"] is True
    assert ("stream_assistant.mode", "game") in calls
    assert ("streaming_stt.enabled", True) in calls
    assert ("streaming_stt.provider", "deepgram") in calls
    assert ("streaming_stt.always_on", True) in calls
    assert ("streaming_stt.submit.min_chars", 4) in calls
    assert ("streaming_stt.submit.debounce_ms", 1200) in calls
    assert ("streaming_stt.submit.max_wait_ms", 4000) in calls
    assert ("streaming_stt.submit.require_speech_final", False) in calls
    assert ("voice.auto_tts", True) in calls
    assert ("tts.aquestalk.koe_generation.timeout_ms", 3000) in calls
    assert ("live_overlay.enabled", True) in calls
    assert ("youtube_chat.overlay.enabled", True) in calls
    assert ("youtube_chat.selection.selected_only", True) in calls


def test_apply_stream_game_mode_reports_failed_writes():
    def saver(key, value):
        return key != "voice.auto_tts"

    result = apply_stream_mode("game", saver=saver)

    assert result["success"] is False
    assert result["failed"] == [
        {
            "key": "voice.auto_tts",
            "value": True,
            "description": "/voice on で TTS も有効にする",
        }
    ]
    assert "voice.auto_tts" in format_apply_result(result)


def test_apply_stream_mode_rejects_unknown_mode():
    result = apply_stream_mode("coding", saver=lambda _key, _value: True)

    assert result["success"] is False
    assert result["supported_modes"] == ["game"]


def test_stream_mode_status_is_shape_safe():
    status = stream_mode_status(
        {
            "stream_assistant": {"mode": "game"},
            "streaming_stt": {
                "enabled": True,
                "provider": "deepgram",
                "always_on": True,
                "submit": {
                    "min_chars": 4,
                    "debounce_ms": 1200,
                    "max_wait_ms": 4000,
                    "require_speech_final": False,
                },
            },
            "voice": {"auto_tts": True},
            "tts": {
                "provider": "aquestalk",
                "aquestalk": {"koe_generation": {"timeout_ms": 3000}},
            },
            "live_overlay": {"enabled": True},
            "youtube_chat": {
                "overlay": {"enabled": True},
                "selection": {"selected_only": True},
            },
        }
    )

    assert status["mode"] == "game"
    assert status["streaming_stt_enabled"] is True
    assert status["streaming_stt_provider"] == "deepgram"
    assert status["streaming_stt_always_on"] is True
    assert status["streaming_stt_min_chars"] == 4
    assert status["streaming_stt_debounce_ms"] == 1200
    assert status["streaming_stt_max_wait_ms"] == 4000
    assert status["streaming_stt_require_speech_final"] is False
    assert status["voice_auto_tts"] is True
    assert status["tts_provider"] == "aquestalk"
    assert status["aquestalk_koe_timeout_ms"] == 3000
    assert status["live_overlay_enabled"] is True
    assert status["youtube_chat_overlay_enabled"] is True
    assert status["youtube_chat_selected_only"] is True
    assert "Voice auto TTS:        ON" in format_status(status)
    assert "STT speech_final req:  OFF" in format_status(status)
