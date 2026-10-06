"""테스트 전용 fault injection. 운영에서는 아무 지점도 활성화되지 않는다(빈 집합)."""
from __future__ import annotations

_active: set[str] = set()


class InjectedFault(RuntimeError):
    pass


def enable(*names: str) -> None:
    _active.update(names)


def clear() -> None:
    _active.clear()


def maybe(name: str) -> None:
    if name in _active:
        raise InjectedFault(f"fault injected at {name}")
