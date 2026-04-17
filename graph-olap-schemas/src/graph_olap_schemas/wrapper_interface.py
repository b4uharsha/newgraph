"""Wrapper interface and types for graph database wrappers."""

from enum import StrEnum


class WrapperType(StrEnum):
    """Supported graph database wrapper types."""

    RYUGRAPH = "ryugraph"
    FALKORDB = "falkordb"
