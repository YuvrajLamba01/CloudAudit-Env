from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class ActionType(StrEnum):
    scan_resources = "scan_resources"
    fix_s3_public_access = "fix_s3_public_access"
    encrypt_database = "encrypt_database"
    restrict_security_group = "restrict_security_group"
    update_iam_policy = "update_iam_policy"
    noop = "noop"


class AuditAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    target_resource: str | None = None
    notes: str | None = None


class ResourceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    s3_public_access_blocked: bool
    iam_least_privilege: bool
    db_encrypted_at_rest: bool
    security_group_restricted: bool


class IssueState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    title: str
    severity: Severity
    fixed: bool = False
    required_action: ActionType
    resource_id: str
    prerequisites: list[str] = Field(default_factory=list)


class ActionLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    action_type: ActionType
    reward: float = Field(ge=0.0, le=1.0)
    error: str | None = None


class AuditReward(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=0.0, le=1.0)
    details: dict[str, float] = Field(default_factory=dict)


class AuditObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    difficulty: Difficulty
    discovered: bool
    current_issues: list[IssueState] = Field(default_factory=list)
    resource_state: ResourceState
    previous_actions: list[ActionLog] = Field(default_factory=list)
    progress_score: float = Field(ge=0.0, le=1.0)
    steps_remaining: int = Field(ge=0)
    last_action_error: str | None = None


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    title: str
    difficulty: Difficulty
    description: str
    max_steps: int = Field(ge=1)
    initial_resources: ResourceState
    issues: list[IssueState]


class AuditState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: TaskSpec
    resources: ResourceState
    issues: list[IssueState]
    discovered: bool = False
    step_count: int = Field(default=0, ge=0)
    invalid_actions: int = Field(default=0, ge=0)
    repeated_actions: int = Field(default=0, ge=0)
    workflow_violations: int = Field(default=0, ge=0)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    done: bool = False
    pending_verification: bool = False
    verification_scans: int = Field(default=0, ge=0)
    fixes_applied: list[ActionType] = Field(default_factory=list)
    action_history: list[ActionLog] = Field(default_factory=list)
    last_action_error: str | None = None
