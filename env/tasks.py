from __future__ import annotations

from .models import ActionType, Difficulty, IssueState, ResourceState, Severity, TaskSpec


TASKS: dict[str, TaskSpec] = {
    "easy_public_s3": TaskSpec(
        task_id="easy_public_s3",
        title="Fix a publicly exposed S3 bucket",
        difficulty=Difficulty.easy,
        description="Run a cloud audit scan and block public access on a critical bucket.",
        max_steps=4,
        initial_resources=ResourceState(
            s3_public_access_blocked=False,
            iam_least_privilege=True,
            db_encrypted_at_rest=True,
            security_group_restricted=True,
        ),
        issues=[
            IssueState(
                issue_id="S3_PUBLIC",
                title="S3 bucket allows public read access",
                severity=Severity.high,
                required_action=ActionType.fix_s3_public_access,
                resource_id="s3://prod-audit-logs",
                prerequisites=[],
            )
        ],
    ),
    "medium_network_data": TaskSpec(
        task_id="medium_network_data",
        title="Fix data and network exposure",
        difficulty=Difficulty.medium,
        description=(
            "Scan resources and remediate unencrypted database storage and open network ingress."
        ),
        max_steps=7,
        initial_resources=ResourceState(
            s3_public_access_blocked=True,
            iam_least_privilege=True,
            db_encrypted_at_rest=False,
            security_group_restricted=False,
        ),
        issues=[
            IssueState(
                issue_id="DB_UNENCRYPTED",
                title="Production database is not encrypted at rest",
                severity=Severity.critical,
                required_action=ActionType.encrypt_database,
                resource_id="rds-prod-main",
                prerequisites=[],
            ),
            IssueState(
                issue_id="SG_OPEN",
                title="Security group exposes admin port to 0.0.0.0/0",
                severity=Severity.high,
                required_action=ActionType.restrict_security_group,
                resource_id="sg-frontend-admin",
                prerequisites=[],
            ),
        ],
    ),
    "hard_full_stack": TaskSpec(
        task_id="hard_full_stack",
        title="Full cloud posture remediation",
        difficulty=Difficulty.hard,
        description=(
            "Resolve an interconnected incident: public object storage, weak IAM policy, open security group, and unencrypted database. "
            "Database encryption requires both IAM hardening and network lockdown."
        ),
        max_steps=12,
        initial_resources=ResourceState(
            s3_public_access_blocked=False,
            iam_least_privilege=False,
            db_encrypted_at_rest=False,
            security_group_restricted=False,
        ),
        issues=[
            IssueState(
                issue_id="S3_PUBLIC",
                title="S3 bucket allows public read access",
                severity=Severity.high,
                required_action=ActionType.fix_s3_public_access,
                resource_id="s3://customer-exports",
                prerequisites=[],
            ),
            IssueState(
                issue_id="IAM_WEAK",
                title="IAM policy includes wildcard admin privileges",
                severity=Severity.critical,
                required_action=ActionType.update_iam_policy,
                resource_id="iam-role/data-pipeline-admin",
                prerequisites=[],
            ),
            IssueState(
                issue_id="SG_OPEN",
                title="Security group exposes admin port to 0.0.0.0/0",
                severity=Severity.high,
                required_action=ActionType.restrict_security_group,
                resource_id="sg-prod-db-access",
                prerequisites=[],
            ),
            IssueState(
                issue_id="DB_UNENCRYPTED",
                title="Production database is not encrypted at rest",
                severity=Severity.critical,
                required_action=ActionType.encrypt_database,
                resource_id="rds-payments-prod",
                prerequisites=["IAM_WEAK", "SG_OPEN"],
            ),
        ],
    ),
}

TASK_ORDER = ["easy_public_s3", "medium_network_data", "hard_full_stack"]


def get_task(task_id: str) -> TaskSpec:
    if task_id not in TASKS:
        raise KeyError(f"Unknown task_id: {task_id}")
    return TASKS[task_id]
