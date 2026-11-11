"""Internal values shared by the dynamic Python adapters."""
from __future__ import annotations

from enum import Enum


class Sentinel(Enum):
    UNSET = "UNSET"
    FLAG_NEEDS_VALUE = "FLAG_NEEDS_VALUE"

    def __repr__(self) -> str:
        return f"Sentinel.{self.name}"


UNSET = Sentinel.UNSET
FLAG_NEEDS_VALUE = Sentinel.FLAG_NEEDS_VALUE
