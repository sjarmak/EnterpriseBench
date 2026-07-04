"""Beta extras, which delegates to gamma's text utility."""
from gamma.textutil import fmt


class Gadget:
    def label(self) -> str:
        return fmt("gadget")
