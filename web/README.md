# Axiom Web GUI

Browser-based Python UI that loads every model from `src/axiomai/model/config.py` and drives a hidden `axiomai chat` terminal session in the background.

Run it from the repository root:

```bash
python web/gui.py --project-root . --open
```

The browser GUI no longer talks to `/v1/chat/completions` directly. It starts `axiomai chat`, selects the matching model from the `model` menu, and reuses that session for replies.

If you only want the terminal version, keep using `python web/tui.py`.

What the web UI does:

- Lets you pick any model from `config.py`
- Keeps conversation state in the browser
- Reuses a hidden `axiomai chat` session for replies
- Lets you change temperature and max tokens for the backend defaults

Useful controls:

- `Enter` sends the message
- `Shift+Enter` inserts a new line
- `Save State` persists the current browser session
- `Restore State` reloads the saved session
- `Export JSON` downloads the conversation

