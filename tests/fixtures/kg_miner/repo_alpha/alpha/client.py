"""Alpha client that consumes beta's Widget."""
from beta import Widget

from .config import Settings


class AlphaClient:
    def __init__(self) -> None:
        self.widget = Widget()
        self.settings = Settings()

    def run(self) -> str:
        return self.widget.ping()
