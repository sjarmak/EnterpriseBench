"""Alpha pipeline that consumes beta's Gadget."""
from beta import Gadget


class Pipeline:
    def run(self) -> str:
        return Gadget().label()
