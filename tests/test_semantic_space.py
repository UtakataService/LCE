from lce_validation.empirical.seed_graph import build_seed_graph
from lce_validation.runtime.semantic_space import load_semantic_cube, resolve_semantic_units
from lce_validation.runtime.utterance_frame import frame_utterance


def test_semantic_cube_is_a_valid_stable_coordinate_registry():
    cube = load_semantic_cube()
    assert cube["pack_id"] == "org.lce.reference.semantic.dialogue"
    assert cube["payload"]["axes"] == ["domain", "speech_act", "interaction", "epistemic", "affect", "reference"]


def test_english_and_japanese_listen_forms_resolve_to_one_language_independent_meaning():
    english = frame_utterance("Please just listen for now.")
    japanese = frame_utterance("\u4eca\u306f\u805e\u3044\u3066\u307b\u3057\u3044\u3002")
    assert english["semantic_ids"] == ("sem.interaction.listen_only",)
    assert japanese["semantic_ids"] == ("sem.interaction.listen_only",)
    assert english["semantic_units"][0]["coordinates"] == japanese["semantic_units"][0]["coordinates"]


def test_multiple_language_labels_can_share_a_single_advice_meaning_unit():
    result = resolve_semantic_units(["advice_request", "advice_permitted"])
    assert result["semantic_ids"] == ["sem.interaction.advice_permitted"]
    assert result["units"][0]["coordinates"]["interaction"] == "advice_permitted"


def test_unmapped_label_is_visible_and_cannot_be_silently_promoted_to_a_meaning_unit():
    result = resolve_semantic_units(["unseen_language_label"])
    assert result["semantic_ids"] == []
    assert result["unmapped_labels"] == ["unseen_language_label"]


def test_seed_graph_projects_semantic_cube_coordinates_without_creating_new_reasoning_edges():
    graph = build_seed_graph("Please just listen for now.", enable_cube=True)
    input_node = next(node for node in graph["nodes"] if node["node_id"] == "input-01")
    assert input_node["semantic_ids"] == ["sem.interaction.listen_only"]
    assert input_node["cube_coords"]["semantic_domain"] == "dialogue"
    assert input_node["cube_coords"]["semantic_speech_act"] == "boundary"
    assert graph["cube"]["axes"][-2:] == ["semantic_domain", "semantic_speech_act"]
