from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = Path(__file__).resolve().parent
for candidate in (str(REPO_ROOT), str(WEB_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

try:
    from web import gui as web_gui
except ModuleNotFoundError:
    import gui as web_gui  # type: ignore


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the legacy server launcher."""
    parser = argparse.ArgumentParser(description="Axiom web server launcher")
    parser.add_argument("--serve", action="store_true", help="Start the web server")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the web server, accepting --serve for backward compatibility."""
    parser = build_argument_parser()
    _, remaining_argv = parser.parse_known_args(argv)
    return web_gui.main(remaining_argv)


if __name__ == "__main__":
    raise SystemExit(main())
