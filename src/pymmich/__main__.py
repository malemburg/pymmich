"""Allow ``python -m pymmich`` and serve as the PyInstaller entry point.

The freeze-time entry script (``scripts/build_pyinstaller.py``) imports
this module's ``app`` so that PyInstaller doesn't have to walk the
installed entry-point metadata at build time — that metadata is
frozen-bundle-unfriendly on some platforms.
"""

from pymmich.cli import app


def main() -> None:
    """Run the pymmich CLI."""
    app()


if __name__ == "__main__":
    main()
