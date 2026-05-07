from unittest.mock import patch

from web.tui import main


def test_main_accepts_serve_and_forwards_server_args():
    with patch("web.tui.web_gui.main", return_value=0) as mock_main:
        result = main(["--serve", "--host", "0.0.0.0", "--port", "9999", "--open"])

    assert result == 0
    mock_main.assert_called_once_with(["--host", "0.0.0.0", "--port", "9999", "--open"])


def test_main_without_serve_still_launches_server():
    with patch("web.tui.web_gui.main", return_value=0) as mock_main:
        result = main([])

    assert result == 0
    mock_main.assert_called_once_with([])
