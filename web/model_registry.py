from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
CONFIG_FILE = SRC_DIR / "axiomai" / "model" / "config.py"
USER_CONFIG_FILE = Path(os.environ.get("AYE_TOKEN_FILE") or (Path.home() / ".ayecfg"))

DEFAULT_MODEL_ID = "google/gemini-3-flash-preview"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048

CUSTOM_MODELS_KEY = "custom_models"


def load_models() -> list[dict[str, Any]]:
    """Load built-in models together with user-configured custom models."""
    built_in_models = _load_builtin_models()
    custom_models = _load_custom_models()
    custom_ids = {model["id"] for model in custom_models}
    merged = custom_models + [model for model in built_in_models if model.get("id") not in custom_ids]
    return [dict(model) for model in merged]


def select_model(models: list[dict[str, Any]], selection: str | int | None) -> dict[str, Any]:
    """Pick a model by index, id, or default model id."""
    if not models:
        raise ValueError("No models are available.")

    if selection is None or str(selection).strip() == "":
        found = next((model for model in models if model.get("id") == DEFAULT_MODEL_ID), None)
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