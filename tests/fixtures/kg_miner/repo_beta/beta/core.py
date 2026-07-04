"""Beta core, which delegates to gamma's helpers."""
from gamma.util import helper
from gamma.util import helper2


class Widget:
    def ping(self) -> str:
        return helper()

    def ping2(self) -> str:
        return helper2()
