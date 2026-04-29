from web.tui import (
    build_messages,
    extract_assistant_text,
    resolve_chat_completions_url,
    select_model,
)


def test_resolve_chat_completions_url_variants():
    assert resolve_chat_completions_url("http://localhost:8000") == "http://localhost:8000/v1/chat/completions"
    assert resolve_chat_completions_url("http://localhost:8000/v1") == "http://localhost:8000/v1/chat/completions"
    assert resolve_chat_completions_url("http://localhost:8000/v1/chat/completions") == "http://localhost:8000/v1/chat/completions"


def test_select_model_by_index_and_id():
    models = [
        {"id": "one", "name": "One"},
        {"id": "two", "name": "Two"},
    ]

    assert select_model(models, "2")["id"] == "two"
    assert select_model(models, "one")["id"] == "one"


def test_build_messages_includes_system_prompt_and_history():
    messages = build_messages(
        "system prompt",
        [{"role": "user", "content": "hello"}],
        "world",
    )

    assert messages == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
    ]


def test_extract_assistant_text_from_common_response_shapes():
    assert extract_assistant_text({"choices": [{"message": {"content": "hello"}}]}) == "hello"
    assert extract_assistant_text({"choices": [{"delta": {"content": "hi"}}]}) == "hi"
