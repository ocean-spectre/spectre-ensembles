"""Shared data types for the SPECTRE agent system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FailureType(Enum):
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    NUMERICAL_BLOWUP = "NUMERICAL_BLOWUP"
    EXF_RANGE_CHECK = "EXF_RANGE_CHECK"
    FILE_IO_CRASH = "FILE_IO_CRASH"
    INITIALIZATION_FAILURE = "INITIALIZATION_FAILURE"
    UNKNOWN = "UNKNOWN"


class HealthStatus(Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class CheckResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class DiagnosisReport:
    failure_type: FailureType
    model_days_reached: float
    wall_time: str
    root_cause: str
    evidence: list[str] = field(default_factory=list)
    suggested_fix: str = ""


@dataclass
class HealthAssessment:
    status: HealthStatus
    model_days: float
    summary: str
    fields: dict[str, str] = field(default_factory=dict)
    trends: str = ""
    recommendation: str = ""


@dataclass
class ValidationCheck:
    name: str
    result: CheckResult
    parameter: str = ""
    current_value: str = ""
    expected_value: str = ""
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[ValidationCheck] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.result == CheckResult.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.result == CheckResult.FAIL)

    @property
    def passed(self) -> bool:
        return self.fail_count == 0


@dataclass
class QCFileResult:
    path: str
    result: CheckResult
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    mean_val: Optional[float] = None
    nan_count: int = 0
    anomalies: list[str] = field(default_factory=list)


@dataclass
class QCReport:
    files: list[QCFileResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for f in self.files if f.result == CheckResult.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.files if f.result == CheckResult.FAIL)


@dataclass
class JobInfo:
    job_id: int
    state: str = ""
    exit_code: str = ""
    elapsed: str = ""
    max_rss: str = ""


@dataclass
class SimulationState:
    """Tracks the current state of the simulation system."""
    active_job_id: Optional[int] = None
    run_dir: str = ""
    last_diagnosis: Optional[DiagnosisReport] = None
    last_health: Optional[HealthAssessment] = None
    model_days: float = 0.0
    cfl_max: float = 0.0
    status: str = "idle"  # idle, running, failed, stopped
