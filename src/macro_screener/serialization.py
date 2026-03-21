from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence, TypeVar, cast

SerializablePrimitive = str | int | float | bool | None
SerializableValue = (
    SerializablePrimitive | list["SerializableValue"] | dict[str, "SerializableValue"]
)

T = TypeVar("T")


class SerializableMixin:
    def to_dict(self) -> dict[str, SerializableValue]:
        data = _serialize(self)
        if not isinstance(data, dict):
            raise TypeError("SerializableMixin.to_dict() requires a dataclass-like object")
        return data


def _serialize(value: Any) -> SerializableValue:
    if is_dataclass(value):
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return cast(SerializablePrimitive, value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_serialize(item) for item in value]
    return cast(SerializablePrimitive, value)


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
