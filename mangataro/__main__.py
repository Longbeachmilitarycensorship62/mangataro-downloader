"""Launch the app: `python -m mangataro` for CLI, `python -m mangataro gui` for GUI."""
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "gui":
        from mangataro.gui import main as gui_main
        gui_main()
    else:
        from mangataro.cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
