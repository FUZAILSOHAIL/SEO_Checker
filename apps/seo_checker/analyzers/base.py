"""
analyzers/base.py — Shared data classes and base analyzer interface.
"""
from __future__ import annotations
from dataclasses import dataclass, field


class Status:
    GOOD    = "good"
    WARNING = "warning"
    ERROR   = "error"
    INFO    = "info"


@dataclass
class Check:
    id: str
    name: str
    status: str          # Status constant
    value: str           # What was actually found (short, display-safe)
    description: str     # One-line human explanation of the finding
    recommendation: str = ""
    points: int = 0      # Points earned
    max_points: int = 10 # Max possible points for this check


@dataclass
class CategoryResult:
    category: str        # snake_case key, e.g. "meta"
    display_name: str    # e.g. "Meta Information"
    score: int           # 0-100
    checks: list = field(default_factory=list)  # list[Check]
    weight: float = 0.2  # contribution to overall score


class BaseAnalyzer:
    category: str     = ""
    display_name: str = ""
    weight: float     = 0.2

    def analyze(self, page_data: dict) -> CategoryResult:
        raise NotImplementedError

    @staticmethod
    def calc_score(checks: list) -> int:
        earned  = sum(c.points for c in checks)
        maximum = sum(c.max_points for c in checks)
        if maximum == 0:
            return 100
        return round((earned / maximum) * 100)
