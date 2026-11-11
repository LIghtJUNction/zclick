# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import enum
import typing as t

class Sentinel(enum.Enum):
    UNSET: object
    FLAG_NEEDS_VALUE: object

    def __repr__(self) -> str:
        ...

    def __copy__(self) -> Sentinel:
        ...

    def __deepcopy__(self, memo: dict[int, t.Any]) -> Sentinel:
        ...

    def __reduce_ex__(self, protocol: object) -> tuple[t.Any, ...]:
        ...
UNSET: t.Literal[Sentinel.UNSET]
FLAG_NEEDS_VALUE: t.Literal[Sentinel.FLAG_NEEDS_VALUE]
T_UNSET: t.TypeAlias = t.Literal[Sentinel.UNSET]
T_FLAG_NEEDS_VALUE: t.TypeAlias = t.Literal[Sentinel.FLAG_NEEDS_VALUE]
