from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import shutil
import textwrap
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

CONFIG_FILE = SRC_DIR / "axiomai" / "model" / "config.py"
USER_CONFIG_FILE = Path(os.environ.get("AYE_TOKEN_FILE") or (Path.home() / ".ayecfg"))

DEFAULT_MODEL_ID = "google/gemini-3-flash-preview"
CUSTOM_MODELS_KEY = "custom_models"


DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048


def load_models() -> list[dict[str, Any]]:
    """Load built-in models together with user-configured custom models."""
    built_in_models = _load_builtin_models()
    custom_models = _load_custom_models()
    custom_ids = {model["id"] for model in custom_models}
    merged = custom_models + [model for model in built_in_models if model.get("id") not in custom_ids]
    return [dict(model) for model in merged]


def _load_builtin_models() -> list[dict[str, Any]]:
    """Parse the MODELS literal from src/axiomai/model/config.py."""
    source = CONFIG_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CONFIG_FILE))

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "MODELS":
                value = ast.literal_eval(node.value)
                if isinstance(value, list):
                    return [dict(model) for model in value if isinstance(model, dict)]

    raise RuntimeError("Could not locate MODELS in src/axiomai/model/config.py")


def _load_custom_models() -> list[dict[str, Any]]:
    """Read custom model definitions from ~/.ayecfg if present."""
    if not USER_CONFIG_FILE.is_file():
        return []

    custom_models_raw: str | None = None
    in_default_section = False
    try:
        for line in USER_CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                in_default_section = stripped[1:-1].strip().lower() == "default"
                continue
            if in_default_section and stripped.startswith(f"{CUSTOM_MODELS_KEY}="):
                custom_models_raw = stripped.split("=", 1)[1].strip()
                break
    except OSError:
        return []

    if not custom_models_raw:
        return []

    try:
        parsed = json.loads(custom_models_raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in parsed:
        model = _normalize_model_entry(item)
        if not model:
            continue
        if model["id"] in seen_ids:
            continue
        seen_ids.add(model["id"])
        normalized.append(model)

    return normalized


def _normalize_model_entry(raw_model: Any) -> dict[str, Any] | None:
    """Validate and normalize a single model dictionary."""
    if not isinstance(raw_model, dict):
        return None

    model_id = str(raw_model.get("id", "")).strip()
    model_name = str(raw_model.get("name", "")).strip()
    if not model_id or not model_name:
        return None

    normalized: dict[str, Any] = {
        "id": model_id,
        "name": model_name,
        "max_prompt_kb": int(raw_model.get("max_prompt_kb", 200)),
        "max_output_tokens": int(raw_model.get("max_output_tokens", 24000)),
        "context_target_kb": int(raw_model.get("context_target_kb", 180)),
    }

    model_type = str(raw_model.get("type", "")).strip().lower()
    if model_type in {"chat", "image", "offline"}:
        normalized["type"] = model_type

    if "size_gb" in raw_model:
        try:
            normalized["size_gb"] = float(raw_model["size_gb"])
        except (TypeError, ValueError):
            pass

    return normalized


def _resolve_openai_endpoint_url(raw_base_url: str | None, endpoint: str) -> str:
    """Normalize a base URL into a specific OpenAI-style endpoint."""
    base_url = (raw_base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if not base_url:
        base_url = DEFAULT_BASE_URL

    if base_url.endswith("/chat/completions") or base_url.endswith("/responses"):
        return base_url

    if endpoint == "responses":
        if base_url.endswith("/v1"):
            return f"{base_url}/responses"
        return f"{base_url}/v1/responses"

    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def resolve_chat_completions_url(raw_base_url: str | None) -> str:
    """Normalize a base URL into a /v1/chat/completions endpoint."""
    return _resolve_openai_endpoint_url(raw_base_url, "chat")


def resolve_responses_url(raw_base_url: str | None) -> str:
    """Normalize a base URL into a /v1/responses endpoint."""
    return _resolve_openai_endpoint_url(raw_base_url, "responses")


def resolve_api_key(explicit_api_key: str | None = None) -> str:
    """Resolve an API key from arguments or common environment variables."""
    if explicit_api_key:
        return explicit_api_key.strip()

    for env_name in ("AXIOM_TUI_API_KEY", "OPENAI_API_KEY", "AYE_TOKEN"):
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            return env_value

    return ""


def select_model(models: list[dict[str, Any]], selection: str | int | None) -> dict[str, Any]:
    """Pick a model by index, id, or default model id."""
    if not models:
        raise ValueError("No models are available.")

    if selection is None or str(selection).strip() == "":
        selected_id = DEFAULT_MODEL_ID
        found = next((model for model in models if model.get("id") == selected_id), None)
        if found:
            return found
        return models[0]

    raw_selection = str(selection).strip()
    try:
        index = int(raw_selection)
    except ValueError:
        index = -1

    if index > 0:
        if index > len(models):
            raise ValueError(f"Model number out of range: {index}")
        return models[index - 1]

    for model in models:
        if model.get("id") == raw_selection:
            return model

    raise ValueError(f"Unknown model selection: {raw_selection}")


def build_messages(system_prompt: str, conversation: Iterable[dict[str, str]], user_text: str) -> list[dict[str, str]]:
    """Build an OpenAI-compatible messages payload."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(dict(message) for message in conversation)
    messages.append({"role": "user", "content": user_text})
    return messages


def build_responses_input(conversation: Iterable[dict[str, str]], user_text: str) -> list[dict[str, str]]:
    """Build an OpenAI Responses API input payload."""
    input_items = [dict(message) for message in conversation]
    input_items.append({"role": "user", "content": user_text})
    return input_items


def _extract_text_from_content(content: Any) -> str:
    """Extract plain text from a Responses or chat/completions content block."""
    if content is None:
        return ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = _extract_text_from_content(item)
            if text:
                parts.append(text)
        return "".join(parts).strip()

    if isinstance(content, dict):
        for key in ("text", "output_text", "content", "value"):
            text = _extract_text_from_content(content.get(key))
            if text:
                return text

    return str(content).strip()


def extract_assistant_text(payload: dict[str, Any]) -> str:
    """Extract assistant text from an OpenAI chat/completions or Responses payload."""
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = payload.get("choices") or []
    if choices:
        first_choice = choices[0] or {}
        message = first_choice.get("message") or {}
        content = message.get("content")
        if content is None:
            content = first_choice.get("text") or first_choice.get("delta", {}).get("content")

        text = _extract_text_from_content(content)
        if text:
            return text

    output = payload.get("output") or []
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            text = _extract_text_from_content(item.get("content") or item.get("text"))
            if text:
                parts.append(text)
        if parts:
            return "".join(parts).strip()

    raise ValueError("The API response did not include any assistant text.")


def render_models_table(models: list[dict[str, Any]], active_model_id: str) -> str:
    """Render the available models as a plain-text table."""
    headers = ["#", "Name", "Model ID", "Type", "Context", "Output"]
    rows: list[list[str]] = []
    for index, model in enumerate(models, 1):
        rows.append([
            str(index),
            str(model.get("name", model.get("id", "unknown"))),
            str(model.get("id", "unknown")),
            str(model.get("type", "chat")),
            f"{model.get('context_target_kb', '-')} KB",
            str(model.get("max_output_tokens", "-")),
        ])

    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def format_row(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))

    separator = "-+-".join("-" * width for width in widths)
    output = ["Available Models", format_row(headers), separator]
    for row in rows:
        prefix = "*" if row[2] == active_model_id else " "
        output.append(prefix + " " + format_row(row))
    return "\n".join(output)


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class TUIState:
    models: list[dict[str, Any]]
    active_model: dict[str, Any]
    api_url: str
    api_key: str
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    conversation: list[ChatTurn] = field(default_factory=list)


class AxiomChatTUI:
    """Small terminal UI for OpenAI-compatible chat/completions APIs."""

    def __init__(self, state: TUIState) -> None:
        self.state = state

    def run(self) -> None:
        self._clear_screen()
        self._print_welcome()

        while True:
            self._render_screen()
            try:
                user_text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                continue

            if user_text.startswith("/"):
                if self._handle_command(user_text):
                    continue

            self.state.conversation.append(ChatTurn(role="user", content=user_text))
            try:
                assistant_text = self._send_chat_completion(user_text)
            except (HTTPError, URLError, ValueError, RuntimeError) as exc:
                print(f"\n[Request failed] {exc}\n")
                continue

            self.state.conversation.append(ChatTurn(role="assistant", content=assistant_text))

    def _print_welcome(self) -> None:
        print("Axiom Chat TUI")
        print("OpenAI-compatible /v1/chat/completions or /v1/responses terminal UI")
        print("Use /models, /use <n|model-id>, /api <url>, /key <token>, /reset, /quit")
        print()

    def _render_screen(self) -> None:
        self._clear_screen()
        print(f"Endpoint: {self.state.api_url}")
        print(
            f"Model: {self.state.active_model.get('name', self.state.active_model.get('id', 'unknown'))} "
            f"({self.state.active_model.get('id', 'unknown')})"
        )
        print(f"Temperature: {self.state.temperature}    Max tokens: {self.state.max_tokens}")
        print()

        recent_turns = self.state.conversation[-8:]
        if not recent_turns:
            print("Conversation is empty.")
        else:
            for turn in recent_turns:
                title = "You" if turn.role == "user" else "Assistant"
                print(f"[{title}]")
                wrapped = textwrap.fill(turn.content, width=self._terminal_width())
                print(wrapped)
                print()

        print(self._help_footer())

    def _help_footer(self) -> str:
        footer = (
            "Commands: /models  /use <n|id>  /api <url>  /key <token>  /system <prompt>  "
            "/reset  /help  /quit\n"
            "Anything else is sent as a chat message."
        )
        return footer

    def _clear_screen(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")

    def _terminal_width(self) -> int:
        return max(60, shutil.get_terminal_size((100, 20)).columns)

    def _handle_command(self, command_text: str) -> bool:
        command, _, argument = command_text[1:].partition(" ")
        command = command.lower().strip()
        argument = argument.strip()

        if command in {"quit", "exit"}:
            raise SystemExit(0)

        if command == "help":
            print(self._help_footer())
            return True

        if command == "models":
            print(render_models_table(self.state.models, self.state.active_model.get("id", "")))
            return True

        if command == "use":
            if not argument:
                print("Usage: /use <model-number|model-id>")
                return True
            self.state.active_model = select_model(self.state.models, argument)
            print(f"Selected model: {self.state.active_model.get('name')} ({self.state.active_model.get('id')})")
            return True

        if command == "api":
            if not argument:
                print("Usage: /api <base-url-or-full-chat-completions-or-responses-url>")
                return True
            current_mode = "responses" if self.state.api_url.rstrip("/").endswith("/responses") else "chat"
            self.state.api_url = (
                resolve_responses_url(argument)
                if current_mode == "responses"
                else resolve_chat_completions_url(argument)
            )
            print(f"API endpoint updated: {self.state.api_url}")
            return True

        if command == "key":
            if not argument:
                print("Usage: /key <token>")
                return True
            self.state.api_key = argument
            print("API key updated for this session.")
            return True

        if command == "system":
            if not argument:
                print("Usage: /system <prompt>")
                return True
            self.state.system_prompt = argument
            print("System prompt updated.")
            return True

        if command == "reset":
            self.state.conversation.clear()
            print("Conversation cleared.")
            return True

        print(f"Unknown command: {command_text}")
        return True

    def _send_chat_completion(self, user_text: str) -> str:
        current_mode = "responses" if self.state.api_url.rstrip("/").endswith("/responses") else "chat"
        if current_mode == "responses":
            payload = {
                "model": self.state.active_model["id"],
                "instructions": self.state.system_prompt,
                "input": build_responses_input(
                    ({"role": turn.role, "content": turn.content} for turn in self.state.conversation[:-1]),
                    user_text,
                ),
                "temperature": self.state.temperature,
                "max_output_tokens": self.state.max_tokens,
                "stream": False,
            }
        else:
            payload = {
                "model": self.state.active_model["id"],
                "messages": build_messages(
                    self.state.system_prompt,
                    ({"role": turn.role, "content": turn.content} for turn in self.state.conversation[:-1]),
                    user_text,
                ),
                "temperature": self.state.temperature,
                "max_tokens": self.state.max_tokens,
                "stream": False,
            }

        headers = {"Content-Type": "application/json"}
        if self.state.api_key:
            headers["Authorization"] = f"Bearer {self.state.api_key}"

        request = Request(
            self.state.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(request, timeout=120.0) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Failed to reach API endpoint: {exc.reason}") from exc

        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"The API returned invalid JSON: {raw_body[:200]}") from exc

        assistant_text = extract_assistant_text(data)
        if not assistant_text:
            raise ValueError("The API returned an empty assistant message.")

        print("\n[Assistant]")
        print(textwrap.fill(assistant_text, width=self._terminal_width()))
        print()
        return assistant_text


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the TUI launcher."""
    parser = argparse.ArgumentParser(description="Axiom OpenAI-compatible chat/completions TUI")
    parser.add_argument("--base-url", default=os.environ.get("AXIOM_TUI_BASE_URL") or os.environ.get("OPENAI_BASE_URL"), help="API base URL or full /v1/chat/completions or /v1/responses URL")
    parser.add_argument("--api-key", default=None, help="API key for this session")
    parser.add_argument("--model", default=None, help="Model number or model id to start with")
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT, help="System prompt for the chat session")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="Maximum completion tokens")
    parser.add_argument("--list-models", action="store_true", help="Print the model list and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Axiom TUI."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    models = load_models()
    if args.list_models:
        print(render_models_table(models, ""))
        return 0

    active_model = select_model(models, args.model)
    state = TUIState(
        models=models,
        active_model=active_model,
        api_url=resolve_chat_completions_url(args.base_url),
        api_key=resolve_api_key(args.api_key),
        system_prompt=args.system_prompt,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    AxiomChatTUI(state).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
