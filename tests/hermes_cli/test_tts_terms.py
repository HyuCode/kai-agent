import json


def test_tts_terms_add_find_and_usage_count(tmp_path):
    from hermes_cli.tts_terms import add_tts_term, find_relevant_tts_terms, list_tts_terms

    db_path = tmp_path / "terms.db"
    add_tts_term("OBS", "おーびーえす", db_path=db_path)
    add_tts_term("YouTube", "ゆーちゅーぶ", db_path=db_path)
    add_tts_term("Unrelated", "よまない", db_path=db_path)

    assert find_relevant_tts_terms("OBSとYouTubeを確認", db_path=db_path) == {
        "OBS": "おーびーえす",
        "YouTube": "ゆーちゅーぶ",
    }

    rows = list_tts_terms(db_path=db_path)
    used = {row["term"]: row["usage_count"] for row in rows}
    assert used["OBS"] == 1
    assert used["YouTube"] == 1
    assert used["Unrelated"] == 0


def test_tts_terms_upsert_and_delete(tmp_path):
    from hermes_cli.tts_terms import add_tts_term, delete_tts_term, find_relevant_tts_terms

    db_path = tmp_path / "terms.db"
    add_tts_term("LLM", "えるえるえむ", db_path=db_path)
    add_tts_term("LLM", "えるえるえむー", source="correction", db_path=db_path)

    assert find_relevant_tts_terms("LLMを使う", db_path=db_path) == {
        "LLM": "えるえるえむー",
    }
    assert delete_tts_term("LLM", db_path=db_path) is True
    assert find_relevant_tts_terms("LLMを使う", db_path=db_path) == {}


def test_import_tts_terms_json(tmp_path):
    from hermes_cli.tts_terms import find_relevant_tts_terms, import_tts_terms_json

    json_path = tmp_path / "terms.json"
    db_path = tmp_path / "terms.db"
    json_path.write_text(
        json.dumps({"GitHub": "ぎっとはぶ", "OBS": "おーびーえす"}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert import_tts_terms_json(json_path, db_path=db_path) == 2
    assert find_relevant_tts_terms("GitHubとOBS", db_path=db_path) == {
        "GitHub": "ぎっとはぶ",
        "OBS": "おーびーえす",
    }


def test_tts_terms_confidence_filter(tmp_path):
    from hermes_cli.tts_terms import add_tts_term, find_relevant_tts_terms

    db_path = tmp_path / "terms.db"
    add_tts_term("Maybe", "めいびー", confidence=0.2, db_path=db_path)
    add_tts_term("Sure", "しゅあ", confidence=0.9, db_path=db_path)

    assert find_relevant_tts_terms(
        "Maybe and Sure",
        min_confidence=0.5,
        db_path=db_path,
    ) == {"Sure": "しゅあ"}
