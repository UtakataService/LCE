from lce_validation.runtime.japanese_dialogue import respond_japanese


def test_wave20_japanese_data_candidates_are_loaded_as_data_not_source_branches():
    cases = {
        "これを分かりやすく説明して": "explanation",
        "内容を要約して": "summary_request",
        "AとBを比較して": "comparison_request",
        "前の内容を訂正する": "correction_acknowledgement",
        "分からないことがある": "uncertainty_acknowledgement",
    }
    for text, expected_act in cases.items():
        result = respond_japanese(text, [])
        assert result["dialogue_act"] == expected_act
        assert result["evidence_id"].startswith("ja-daily-")


def test_wave20_continuation_candidate_requires_history():
    assert respond_japanese("さっきの続き", [])["match_decision"] == "REJECT"
    result = respond_japanese("さっきの続き", [{"speaker": "user", "text": "モデルを比較したい"}])
    assert result["dialogue_act"] == "continuation_request"


def test_wave20_ten_data_loops_load_distinct_japanese_dialogue_operations():
    cases = [
        ("この文章を言い換えて", "rephrase_request"),
        ("段階的な手順を示して", "procedure_request"),
        ("選択肢を並べて", "options_request"),
        ("アイデアを三つ出して", "ideation_request"),
        ("計画の骨子を作って", "planning_request"),
        ("質問を一つずつして", "guided_questioning"),
        ("結論を先に教えて", "answer_style_request"),
        ("英語に翻訳して", "translation_request"),
        ("日本語に翻訳して", "translation_request"),
        ("前提を整理して", "assumption_request"),
    ]
    for text, act in cases:
        result = respond_japanese(text, [])
        assert result["dialogue_act"] == act
        assert result["evidence_id"].startswith("ja-wave20-")
