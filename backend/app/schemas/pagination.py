"""Shared pagination primitives used by every list endpoint."""
from typing import Annotated, Generic, List, TypeVar

from litestar.params import QueryParameter
from pydantic import BaseModel

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
DEFAULT_MESSAGE_PAGE_SIZE = 100
MAX_MESSAGE_PAGE_SIZE = 500

LimitParam = Annotated[
    int,
    QueryParameter(name="limit", ge=1, le=MAX_PAGE_SIZE),
]
OffsetParam = Annotated[
    int,
    QueryParameter(name="offset", ge=0),
]
MessageLimitParam = Annotated[
    int,
    QueryParameter(name="limit", ge=1, le=MAX_MESSAGE_PAGE_SIZE),
]


class Page(BaseModel, Generic[T]):
    """Envelope for every paginated list response."""

    items: List[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total
