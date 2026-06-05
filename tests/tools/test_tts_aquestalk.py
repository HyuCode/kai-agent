"""Tests for the AquesTalk TTS provider in tools/tts_tool.py."""

import json
from unittest.mock import patch


def test_aquestalk_normalization_uses_configured_terms():
    from tools.tts_tool import _normalize_aquestalk_text

    normalized = _normalize_aquestalk_text(
        "**OBS**とYouTubeチャットを見ます!",
        {"terms": {"OBS": "おーびーえす", "YouTube": "ゆーちゅーぶ"}},
    )

    assert normalized == "おーびーえすとゆーちゅーぶちゃっとを見ます。"


def test_aquestalk_normalization_uses_relevant_db_terms(tmp_path):
    from hermes_cli.tts_terms import add_tts_term
    from tools.tts_tool import _normalize_aquestalk_text

    db_path = tmp_path / "tts_terms.db"
    add_tts_term("OBS", "おーびーえす", db_path=db_path)
    add_tts_term("YouTube", "ゆーちゅーぶ", db_path=db_path)
    add_tts_term("Unrelated", "よまない", db_path=db_path)

    normalized = _normalize_aquestalk_text(
        "OBSとYouTubeを確認します。",
        {"terms_db_path": str(db_path)},
    )

    assert normalized == "おーびーえすとゆーちゅーぶを確認します。"


def test_aquestalk_normalization_can_disable_db_terms(tmp_path):
    from hermes_cli.tts_terms import add_tts_term
    from tools.tts_tool import _normalize_aquestalk_text

    db_path = tmp_path / "tts_terms.db"
    add_tts_term("OBS", "おーびーえす", db_path=db_path)

    normalized = _normalize_aquestalk_text(
        "OBSを確認します。",
        {"terms_db_path": str(db_path), "terms_db_enabled": False},
    )

    assert normalized == "OBSを確認します。"


def test_aquestalk_koe_sanitizer_keeps_only_safe_reading_chars():
    from tools.tts_tool import _sanitize_aquestalk_koe

    sanitized = _sanitize_aquestalk_koe('```text\n出力: ゆーちゅーぶで/かくにんします! OBS\n```')

    assert sanitized == "ゆーちゅーぶで/かくにんします。"


def test_aquestalk_particle_pronunciation_for_segment_final_particles():
    from tools.tts_tool import _sanitize_aquestalk_koe

    sanitized = _sanitize_aquestalk_koe("こんにちは、ちょうしは/どうですか？ みぎへ。こえを。")

    assert sanitized == "こんにちわ、ちょうしわ/どうですか？みぎえ。こえお。"


def test_aquestalk_prepare_skips_llm_for_safe_kana_text():
    from tools.tts_tool import _prepare_aquestalk_text

    with patch("requests.post") as post:
        prepared = _prepare_aquestalk_text(
            "こんにちは、こえを。みぎへ。",
            {"koe_generation": {"enabled": True}},
        )

    assert prepared == "こんにちわ、こえお。みぎえ。"
    post.assert_not_called()


def test_aquestalk_koe_generation_uses_openai_compatible_llm():
    from tools.tts_tool import _prepare_aquestalk_text

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "つぎに/みぎえ/すすみます。"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["timeout"] = kwargs["timeout"]
        return FakeResponse()

    config = {
        "koe_generation": {
            "enabled": True,
            "base_url": "http://local-llm:8001/v1",
            "model": "gemma-4-e4b",
            "timeout_ms": 2500,
        },
    }
    with patch("requests.post", side_effect=fake_post):
        prepared = _prepare_aquestalk_text("次に右へ進みます。", config)

    assert prepared == "つぎに/みぎえ/すすみます。"
    assert captured["url"] == "http://local-llm:8001/v1/chat/completions"
    assert captured["json"]["model"] == "gemma-4-e4b"
    assert captured["json"]["messages"][1]["content"] == "次に右へ進みます。"
    assert captured["timeout"] == 2.5


def test_aquestalk_koe_generation_falls_back_to_normalizer_on_failure():
    from tools.tts_tool import _prepare_aquestalk_text

    config = {
        "koe_generation": {
            "enabled": True,
            "base_url": "http://local-llm:8001/v1",
        },
        "terms": {"確認": "かくにん"},
    }
    with patch("requests.post", side_effect=RuntimeError("offline")):
        prepared = _prepare_aquestalk_text("確認します。", config)

    assert prepared == "かくにんします。"


def test_aquestalk_generation_passes_llm_koe_to_cli(tmp_path):
    from tools.tts_tool import _generate_aquestalk_tts

    output_path = tmp_path / "out.wav"

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "つぎに/みぎえ/すすみます。"}}]}

    with patch("requests.post", return_value=FakeResponse()), patch(
        "tools.tts_tool._run_aquestalk_cli",
        return_value=b"RIFFwav",
    ) as run:
        result = _generate_aquestalk_tts(
            "次に右へ進みます。",
            str(output_path),
            {
                "aquestalk": {
                    "cli_path": "/bin/echo",
                    "koe_generation": {"enabled": True, "base_url": "http://local-llm:8001/v1"},
                },
            },
        )

    assert result == str(output_path)
    assert run.call_args.args[0] == "つぎに/みぎえ/すすみます。"


def test_aquestalk_generation_logs_quality_metrics(tmp_path, caplog):
    from tools.tts_tool import _generate_aquestalk_tts

    output_path = tmp_path / "out.wav"

    with caplog.at_level("INFO", logger="tools.tts_tool"), patch(
        "tools.tts_tool._run_aquestalk_cli",
        return_value=b"RIFFwav",
    ):
        result = _generate_aquestalk_tts(
            "こんにちは。",
            str(output_path),
            {"aquestalk": {"cli_path": "/bin/echo", "log_text": True}},
        )

    assert result == str(output_path)
    assert "AquesTalk TTS quality success=True source=deterministic" in caplog.text
    assert "AquesTalk TTS text original='こんにちは。' prepared='こんにちわ。'" in caplog.text


def test_aquestalk_wav_generation_writes_cli_stdout(tmp_path):
    from tools.tts_tool import _generate_aquestalk_tts

    output_path = tmp_path / "out.wav"

    with patch("tools.tts_tool._run_aquestalk_cli", return_value=b"RIFFwav") as run:
        result = _generate_aquestalk_tts(
            "こんにちは",
            str(output_path),
            {"aquestalk": {"cli_path": "/bin/echo", "lib_dir": "/tmp/lib", "voice": "F2", "speed": 130}},
        )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"RIFFwav"
    assert run.call_args.kwargs["voice"] == "F2"
    assert run.call_args.kwargs["speed"] == 130
    assert run.call_args.kwargs["lib_dir"] == "/tmp/lib"


def test_aquestalk_mp3_generation_converts_via_ffmpeg(tmp_path):
    from tools.tts_tool import _generate_aquestalk_tts

    output_path = tmp_path / "out.mp3"

    def fake_convert(input_path, out_path, output_format):
        assert output_format == "mp3"
        assert out_path == str(output_path)
        with open(out_path, "wb") as f:
            f.write(b"mp3")

    with patch("tools.tts_tool._run_aquestalk_cli", return_value=b"RIFFwav"), patch(
        "tools.tts_tool._ffmpeg_convert_audio",
        side_effect=fake_convert,
    ):
        result = _generate_aquestalk_tts(
            "こんにちは",
            str(output_path),
            {"aquestalk": {"cli_path": "/bin/echo"}},
        )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"mp3"


def test_aquestalk_cli_receives_license_keys_via_env_not_args(monkeypatch):
    from tools.tts_tool import _run_aquestalk_cli

    captured = {}

    class FakeProc:
        returncode = 0
        stdout = b"RIFFwav"
        stderr = b""

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return FakeProc()

    monkeypatch.setenv("AQUESTALK_DEV_KEY", "dev-secret")
    monkeypatch.setenv("AQUESTALK_USR_KEY", "usr-secret")
    monkeypatch.setattr("os.path.isfile", lambda _path: True)
    monkeypatch.setattr("os.access", lambda _path, _mode: True)

    with patch("subprocess.run", side_effect=fake_run):
        result = _run_aquestalk_cli(
            "こんにちは。",
            cli_path="/opt/aquestalk/aquestalk_cli",
            lib_dir="/opt/aquestalk/lib",
            voice="F1",
            speed=120,
            timeout=10,
            config={"pitch": 110},
        )

    assert result == b"RIFFwav"
    assert "dev-secret" not in captured["args"]
    assert "usr-secret" not in captured["args"]
    assert captured["env"]["AQUESTALK_DEV_KEY"] == "dev-secret"
    assert captured["env"]["AQUESTALK_USR_KEY"] == "usr-secret"
    assert captured["env"]["DYLD_LIBRARY_PATH"] == "/opt/aquestalk/lib"
    assert captured["args"] == [
        "/opt/aquestalk/aquestalk_cli",
        "こんにちは。",
        "F1",
        "120",
        "--pit=110",
    ]


def test_dispatcher_routes_to_aquestalk(tmp_path):
    from tools.tts_tool import text_to_speech_tool

    output_path = str(tmp_path / "out.mp3")

    def fake_aquestalk(text, out, config):
        assert text == "こんにちは"
        assert out == output_path
        assert config["provider"] == "aquestalk"
        with open(out, "wb") as f:
            f.write(b"audio")
        return out

    with patch(
        "tools.tts_tool._load_tts_config",
        return_value={"provider": "aquestalk", "aquestalk": {"cli_path": "/bin/echo"}},
    ), patch("tools.tts_tool._generate_aquestalk_tts", side_effect=fake_aquestalk):
        result = json.loads(text_to_speech_tool("こんにちは", output_path=output_path))

    assert result["success"] is True
    assert result["provider"] == "aquestalk"
    assert result["file_path"] == output_path


def test_check_tts_requirements_accepts_aquestalk(monkeypatch):
    from tools.tts_tool import check_tts_requirements

    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    with patch("tools.tts_tool._has_any_command_tts_provider", return_value=False), \
         patch("tools.tts_tool._import_edge_tts", side_effect=ImportError), \
         patch("tools.tts_tool._import_elevenlabs", side_effect=ImportError), \
         patch("tools.tts_tool._import_openai_client", side_effect=ImportError), \
         patch("tools.tts_tool._has_openai_audio_backend", return_value=False), \
         patch("tools.tts_tool._check_aquestalk_available", return_value=True), \
         patch("tools.tts_tool._check_neutts_available", return_value=False), \
         patch("tools.tts_tool._check_kittentts_available", return_value=False), \
         patch("tools.tts_tool._check_piper_available", return_value=False):
        assert check_tts_requirements() is True
