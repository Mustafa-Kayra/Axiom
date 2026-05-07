from web.tui import (
    build_messages,
    build_responses_input,
    extract_assistant_text,
    resolve_chat_completions_url,
    resolve_responses_url,
    select_model,
)


def test_resolve_chat_completions_url_variants():
    assert resolve_chat_completions_url("http://localhost:8000") == "http://localhost:8000/v1/chat/completions"
    assert resolve_chat_completions_url("http://localhost:8000/v1") == "http://localhost:8000/v1/chat/completions"
    assert resolve_chat_completions_url("http://localhost:8000/v1/chat/completions") == "http://localhost:8000/v1/chat/completions"
    assert resolve_chat_completions_url("http://localhost:8000/v1/responses") == "http://localhost:8000/v1/responses"


def test_resolve_responses_url_variants():
    assert resolve_responses_url("http://localhost:8000") == "http://localhost:8000/v1/responses"
    assert resolve_responses_url("http://localhost:8000/v1") == "http://localhost:8000/v1/responses"
    assert resolve_responses_url("http://localhost:8000/v1/responses") == "http://localhost:8000/v1/responses"


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


def test_build_responses_input_includes_history_and_user_message():
    messages = build_responses_input(
        [{"role": "user", "content": "hello"}],
        "world",
    )

    assert messages == [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
    ]


def test_extract_assistant_text_from_common_response_shapes():
    assert extract_assistant_text({"choices": [{"message": {"content": "hello"}}]}) == "hello"
    assert extract_assistant_text({"choices": [{"delta": {"content": "hi"}}]}) == "hi"
    assert extract_assistant_text({"output_text": "hey"}) == "hey"
    assert extract_assistant_text(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hola"}],
                }
            ]
        }
    ) == "hola"
