"""Parser interface — common data structures for all parsers."""

from dataclasses import dataclass, field


@dataclass
class ParsedFeature:
    name: str
    type: str  # SO term: CDS, promoter, terminator, etc.
    start: int  # 0-indexed
    end: int
    strand: int  # +1 or -1
    qualifiers: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedPrimer:
    name: str
    sequence: str
    tm: float | None = None
    start: int | None = None
    end: int | None = None
    strand: int | None = None


@dataclass
class ParseResult:
    name: str
    sequence: str
    size_bp: int
    topology: str  # 'circular' | 'linear'
    description: str | None = None
    features: list[ParsedFeature] = field(default_factory=list)
    primers: list[ParsedPrimer] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
