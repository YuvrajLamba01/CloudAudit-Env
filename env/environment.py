from __future__ import annotations

from copy import deepcopy

from .graders import grade_state
from .models import (
    ActionLog,
    ActionType,
    AuditAction,
    AuditObservation,
    AuditReward,
    AuditState,
    IssueState,
    ResourceState,
)
from .tasks import TASK_ORDER, get_task


class CloudAuditEnv:
    def __init__(self, task_id: str | None = None):
        self._task_id = task_id or TASK_ORDER[0]
        self._state: AuditState | None = None
        self.reset(task_id=self._task_id)

    def reset(self, task_id: str | None = None) -> AuditObservation:
        if task_id is not None:
            self._task_id = task_id

        task = get_task(self._task_id)
        self._state = AuditState(
            task=task,
            resources=task.initial_resources.model_copy(deep=True),
            issues=[issue.model_copy(deep=True) for issue in task.issues],
            discovered=False,
            step_count=0,
            invalid_actions=0,
            repeated_actions=0,
            workflow_violations=0,
            score=0.0,
            done=False,
            pending_verification=False,
            verification_scans=0,
            fixes_applied=[],
            action_history=[],
            last_action_error=None,
        )
        return self._observation()

    def state(self) -> AuditState:
        return self._require_state().model_copy(deep=True)

    def close(self) -> None:
        return None

    def step(self, action: AuditAction | dict) -> tuple[AuditObservation, AuditReward, bool, dict]:
        state = self._require_state()
        if state.done:
            reward = AuditReward(value=0.0, score=state.score, details={"final": state.score})
            return self._observation(), reward, True, {"last_action_error": "episode_done"}

        parsed = action if isinstance(action, AuditAction) else AuditAction.model_validate(action)
        previous_score = state.score
        error = self._apply_action(state, parsed)

        state.step_count += 1
        state.last_action_error = error

        score, details = grade_state(state, state.task)
        state.score = score

        all_fixed = all(issue.fixed for issue in state.issues)
        requires_final_verification = state.task.task_id == "hard_full_stack"
        verification_complete = (not state.pending_verification) and state.verification_scans >= 2
        state.done = (
            (all_fixed and (not requires_final_verification or verification_complete))
            or state.step_count >= state.task.max_steps
        )

        reward = AuditReward(value=max(state.score - previous_score, 0.0), score=state.score, details=details)

        state.action_history.append(
            ActionLog(
                step=state.step_count,
                action_type=parsed.action_type,
                reward=reward.value,
                error=error,
            )
        )

        obs = self._observation()
        info = {
            "task_id": state.task.task_id,
            "last_action_error": error,
            "fixes_applied": [fix.value for fix in state.fixes_applied],
            "issues_fixed": sum(1 for issue in state.issues if issue.fixed),
            "issues_total": len(state.issues),
            "score_breakdown": details,
        }
        return obs, reward, state.done, info

    def _apply_action(self, state: AuditState, action: AuditAction) -> str | None:
        if action.action_type == ActionType.noop:
            state.repeated_actions += 1
            return "noop_action_penalty"

        if action.action_type == ActionType.scan_resources:
            if not state.discovered:
                state.discovered = True
                state.verification_scans = 1
                return None

            if state.pending_verification:
                state.pending_verification = False
                state.verification_scans += 1
                return None

            state.repeated_actions += 1
            return "scan_repeated"

        if action.target_resource is None:
            state.invalid_actions += 1
            return "target_resource_required"

        if not state.discovered:
            state.invalid_actions += 1
            return "scan_required_before_fix"

        target_issue = self._find_issue_for_action(state.issues, action.action_type)
        if target_issue is None:
            state.invalid_actions += 1
            return "action_not_applicable"

        if action.target_resource != target_issue.resource_id:
            state.invalid_actions += 1
            return "target_resource_mismatch"

        if target_issue.fixed:
            state.repeated_actions += 1
            return "issue_already_fixed"

        if state.task.task_id == "hard_full_stack" and action.action_type == ActionType.encrypt_database:
            if not self._is_issue_fixed(state.issues, "IAM_WEAK") or not self._is_issue_fixed(state.issues, "SG_OPEN"):
                state.workflow_violations += 1
                state.invalid_actions += 1
                return "workflow_violation:encrypt_before_identity_and_network"

        unmet = [issue_id for issue_id in target_issue.prerequisites if not self._is_issue_fixed(state.issues, issue_id)]
        if unmet:
            state.invalid_actions += 1
            return f"unmet_prerequisites:{','.join(unmet)}"

        self._mark_issue_fixed(state, target_issue.issue_id, action.action_type)
        if state.task.task_id == "hard_full_stack":
            state.pending_verification = True
        return None

    @staticmethod
    def _find_issue_for_action(issues: list[IssueState], action_type: ActionType) -> IssueState | None:
        for issue in issues:
            if issue.required_action == action_type:
                return issue
        return None

    @staticmethod
    def _is_issue_fixed(issues: list[IssueState], issue_id: str) -> bool:
        for issue in issues:
            if issue.issue_id == issue_id:
                return issue.fixed
        return False

    def _mark_issue_fixed(self, state: AuditState, issue_id: str, action_type: ActionType) -> None:
        for issue in state.issues:
            if issue.issue_id == issue_id:
                issue.fixed = True

        if issue_id == "S3_PUBLIC":
            state.resources.s3_public_access_blocked = True
        elif issue_id == "IAM_WEAK":
            state.resources.iam_least_privilege = True
        elif issue_id == "DB_UNENCRYPTED":
            state.resources.db_encrypted_at_rest = True
        elif issue_id == "SG_OPEN":
            state.resources.security_group_restricted = True

        state.fixes_applied.append(action_type)

    def _observation(self) -> AuditObservation:
        state = self._require_state()
        visible_issues = [issue.model_copy(deep=True) for issue in state.issues] if state.discovered else []
        steps_remaining = max(state.task.max_steps - state.step_count, 0)

        return AuditObservation(
            task_id=state.task.task_id,
            difficulty=state.task.difficulty,
            discovered=state.discovered,
            current_issues=visible_issues,
            resource_state=state.resources.model_copy(deep=True),
            previous_actions=deepcopy(state.action_history[-5:]),
            progress_score=state.score,
            steps_remaining=steps_remaining,
            last_action_error=state.last_action_error,
        )

    def _require_state(self) -> AuditState:
        if self._state is None:
            raise RuntimeError("Environment has not been initialized")
        return self._state
