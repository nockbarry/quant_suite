"""Entry point: python -m src.tui"""

from src.tui.app import AthenaApp

if __name__ == "__main__":
    app = AthenaApp()
    app.run()
