"""Tests for the Fish Audio TTS provider in tools/tts_tool.py."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("FISH_AUDIO_API_KEY", "HERMES_SESSION_PLATFORM"):
        monkeypatch.delenv(key, raising=False)


class TestGenerateFishAudioTts:
    def test_missing_api_key_raises_value_error(self, tmp_path):
        from tools.tts_tool import _generate_fish_audio_tts

        with pytest.raises(ValueError, match="FISH_AUDIO_API_KEY"):
            _generate_fish_audio_tts(
                "Hello",
                str(tmp_path / "test.mp3"),
                {"fish_audio": {"reference_id": "voice-1"}},
            )

    def test_missing_reference_id_raises_value_error(self, tmp_path, monkeypatch):
        from tools.tts_tool import _generate_fish_audio_tts

        monkeypatch.setenv("FISH_AUDIO_API_KEY", "test-key")

        with pytest.raises(ValueError, match="reference_id"):
            _generate_fish_audio_tts("Hello", str(tmp_path / "test.mp3"), {})

    def test_successful_generation_posts_expected_payload(self, tmp_path, monkeypatch):
        from tools.tts_tool import _generate_fish_audio_tts

        monkeypatch.setenv("FISH_AUDIO_API_KEY", "test-key")
        response = MagicMock()
        response.status_code = 200
        response.content = b"fake-audio"

        with patch("requests.post", return_value=response) as post:
            output_path = str(tmp_path / "test.mp3")
            result = _generate_fish_audio_tts(
                "Hello world",
                output_path,
                {
                    "fish_audio": {
                        "reference_id": "voice-1",
                        "model": "s2-pro",
                        "latency": "balanced",
                        "speed": 1.1,
                    }
                },
            )

        assert result == output_path
        assert (tmp_path / "test.mp3").read_bytes() == b"fake-audio"
        post.assert_called_once()
        call_kwargs = post.call_args.kwargs
        assert post.call_args.args[0] == "https://api.fish.audio/v1/tts"
        assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert call_kwargs["headers"]["model"] == "s2-pro"
        assert call_kwargs["json"]["text"] == "Hello world"
        assert call_kwargs["json"]["reference_id"] == "voice-1"
        assert call_kwargs["json"]["format"] == "mp3"
        assert call_kwargs["json"]["mp3_bitrate"] == 128
        assert call_kwargs["json"]["latency"] == "balanced"
        assert call_kwargs["json"]["prosody"]["speed"] == 1.1

    def test_ogg_output_requests_opus(self, tmp_path, monkeypatch):
        from tools.tts_tool import _generate_fish_audio_tts

        monkeypatch.setenv("FISH_AUDIO_API_KEY", "test-key")
        response = MagicMock(status_code=200, content=b"opus-audio")

        with patch("requests.post", return_value=response) as post:
            _generate_fish_audio_tts(
                "Hi",
                str(tmp_path / "test.ogg"),
                {"fish_audio": {"reference_id": "voice-1"}},
            )

        payload = post.call_args.kwargs["json"]
        assert payload["format"] == "opus"
        assert payload["sample_rate"] == 48000
        assert payload["opus_bitrate"] == 32000
        assert "mp3_bitrate" not in payload

    def test_api_error_includes_status_and_message(self, tmp_path, monkeypatch):
        from tools.tts_tool import _generate_fish_audio_tts

        monkeypatch.setenv("FISH_AUDIO_API_KEY", "test-key")
        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {"message": "bad reference"}

        with patch("requests.post", return_value=response), pytest.raises(
            RuntimeError,
            match="HTTP 422.*bad reference",
        ):
            _generate_fish_audio_tts(
                "Hi",
                str(tmp_path / "test.mp3"),
                {"fish_audio": {"reference_id": "voice-1"}},
            )


class TestTtsDispatcherFishAudio:
    def test_dispatcher_routes_to_fish_audio(self, tmp_path, monkeypatch):
        from tools.tts_tool import text_to_speech_tool

        monkeypatch.setenv("FISH_AUDIO_API_KEY", "test-key")
        output_path = str(tmp_path / "out.mp3")

        def fake_fish(text, out, config):
            assert text == "Hello"
            assert out == output_path
            assert config["provider"] == "fish_audio"
            with open(out, "wb") as f:
                f.write(b"audio")
            return out

        with patch(
            "tools.tts_tool._load_tts_config",
            return_value={"provider": "fish_audio", "fish_audio": {"reference_id": "voice-1"}},
        ), patch("tools.tts_tool._generate_fish_audio_tts", side_effect=fake_fish):
            result = json.loads(text_to_speech_tool("Hello", output_path=output_path))

        assert result["success"] is True
        assert result["provider"] == "fish_audio"
        assert result["file_path"] == output_path

    @pytest.mark.parametrize("alias", ["fish", "fishaudio", "fish-audio"])
    def test_provider_aliases_normalize_to_fish_audio(self, alias):
        from tools.tts_tool import _get_provider

        assert _get_provider({"provider": alias}) == "fish_audio"


class TestCheckTtsRequirementsFishAudio:
    def test_fish_audio_key_returns_true(self, monkeypatch):
        from tools.tts_tool import check_tts_requirements

        monkeypatch.setenv("FISH_AUDIO_API_KEY", "test-key")
        with patch("tools.tts_tool._has_any_command_tts_provider", return_value=False), \
             patch("tools.tts_tool._import_edge_tts", side_effect=ImportError), \
             patch("tools.tts_tool._import_elevenlabs", side_effect=ImportError), \
             patch("tools.tts_tool._import_openai_client", side_effect=ImportError), \
             patch("tools.tts_tool._has_openai_audio_backend", return_value=False), \
             patch("tools.tts_tool._check_neutts_available", return_value=False), \
             patch("tools.tts_tool._check_kittentts_available", return_value=False), \
             patch("tools.tts_tool._check_piper_available", return_value=False):
            assert check_tts_requirements() is True
