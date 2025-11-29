from unittest.mock import patch


def test_cli_main_invokes_uvicorn_run():
    with patch("uvicorn.run") as mock_run:
        # import inside test to ensure patch target is available
        from avanamy.cli import main as cli_main

        cli_main.main()

    mock_run.assert_called_once()
