from web.gui import CHAT_PROMPT_MARKER, _model_index_for_id, _strip_ansi


def test_strip_ansi_removes_escape_sequences():
    assert _strip_ansi("\x1b[31mhello\x1b[0m") == "hello"


def test_model_index_for_id_uses_config_order():
    models = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

    assert _model_index_for_id(models, "a") == 1
    assert _model_index_for_id(models, "c") == 3


def test_chat_prompt_marker_matches_cli_prompt():
    assert CHAT_PROMPT_MARKER == "(ツ» "
