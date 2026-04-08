from __future__ import annotations

from .models import AuditState, TaskSpec


def _completion_component(state: AuditState) -> float:
    total = len(state.issues)
    if total == 0:
        return 1.0
    fixed = sum(1 for issue in state.issues if issue.fixed)
    return fixed / total


def _correctness_component(state: AuditState, task: TaskSpec) -> float:
    if task.max_steps <= 0:
        return 1.0
    penalty_ratio = (
        state.invalid_actions + state.repeated_actions + state.workflow_violations
    ) / task.max_steps
    return max(0.0, 1.0 - penalty_ratio)


def _efficiency_component(state: AuditState) -> float:
    if state.step_count <= 0:
        return 0.0
    if all(issue.fixed for issue in state.issues):
        return 1.0
    fixed_actions = len(state.fixes_applied)
    return min(fixed_actions / state.step_count, 1.0)


def _workflow_component(state: AuditState, task: TaskSpec) -> float:
    if task.task_id != "hard_full_stack":
        return 1.0 if state.discovered else 0.0

    if not state.discovered:
        return 0.0

    if state.verification_scans >= 2 and not state.pending_verification:
        return 1.0

    if state.verification_scans >= 1:
        return 0.5

    return 0.0


def grade_state(state: AuditState, task: TaskSpec) -> tuple[float, dict[str, float]]:
    completion = _completion_component(state)
    correctness = _correctness_component(state, task)
    efficiency = _efficiency_component(state)
    workflow = _workflow_component(state, task)

    score = 0.55 * completion + 0.20 * correctness + 0.15 * efficiency + 0.10 * workflow

    # Small operational cost keeps "excellent" runs realistic instead of always perfect.
    step_ratio = state.step_count / max(task.max_steps, 1)
    execution_cost_factor = 0.02 if task.task_id == "easy_public_s3" else 0.08
    execution_cost = min(execution_cost_factor * step_ratio, execution_cost_factor)
    residual_risk = 0.01 if completion == 1.0 else 0.0
    score -= execution_cost + residual_risk

    score = max(0.0, min(score, 1.0))
    details = {
        "completion": round(completion, 4),
        "correctness": round(correctness, 4),
        "efficiency": round(efficiency, 4),
        "workflow": round(workflow, 4),
        "execution_cost": round(execution_cost, 4),
        "residual_risk": round(residual_risk, 4),
        "final": round(score, 4),
    }
    return score, details
