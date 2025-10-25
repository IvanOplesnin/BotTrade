import enum


class Direction(str, enum.Enum):
    UNKNOWN = "unknown"
    LONG = "long"
    SHORT = "short"
