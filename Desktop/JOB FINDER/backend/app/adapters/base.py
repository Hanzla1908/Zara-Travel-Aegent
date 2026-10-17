"""
Shared types for all job-source adapters.

Each adapter implements BaseAdapter.fetch() and returns AdapterResult.
RawJob is the normalized, source-agnostic job schema. Every adapter
must populate all required fields so callers never need to handle
source-specific shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AdapterQuery:
    keyword: str = ""
    location: str = ""
    experience: list[str] = field(default_factory=list)
    job_type: str = ""          # "Full-time" | "Part-time" | "Contract" | "Remote"
    limit: int = 50


@dataclass
class RawJob:
    """Normalized job representation returned by every adapter."""
    # Deduplication key — must be stable across repeated fetches.
    # Convention: "<source>:<source-assigned-id>"
    external_id: str

    title: str
    company: str
    location: str            # Human-readable city / country string
    description: str
    requirements: list[str]  # Bullet-point requirements extracted from the listing
    salary: str              # Raw string from source, e.g. "PKR 150k–200k/mo"
    source: str              # "linkedin" | "rozee"
    url: str                 # Canonical link to the original listing

    posted_at: datetime | None = None
    location_type: str = "On-site"   # "On-site" | "Remote" | "Hybrid"
    job_type: str = "Full-time"
    experience: str = "Mid"          # "Junior" | "Mid" | "Senior" | "Lead"


@dataclass
class AdapterResult:
    jobs: list[RawJob]
    available: bool
    # Human-readable explanation when available=False (not logged, only returned to caller).
    reason: str = ""


class BaseAdapter(ABC):
    source_id: str = ""
    source_label: str = ""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the required API credentials are present in settings."""
        ...

    @abstractmethod
    async def fetch(self, query: AdapterQuery) -> AdapterResult:
        """
        Fetch jobs matching *query* from this source.

        Must return AdapterResult(jobs=[], available=False, reason=...) when:
          - credentials are missing (is_configured is False)
          - the remote API is temporarily unreachable
          - the source returns an error

        Must NEVER invent jobs or return data not received from the source.
        """
        ...
