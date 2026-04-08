from __future__ import annotations

from pathlib import Path

from env import ActionType, AuditAction, CloudAuditEnv, TASK_ORDER, get_task


def build_heuristic_action(observation) -> AuditAction:
    if not observation.discovered:
        return AuditAction(action_type=ActionType.scan_resources)

    remaining = [issue for issue in observation.current_issues if not issue.fixed]
    required = {issue.required_action.value: issue for issue in remaining}

    if "update_iam_policy" in required:
        issue = required["update_iam_policy"]
        return AuditAction(action_type=ActionType.update_iam_policy, target_resource=issue.resource_id)
    if "restrict_security_group" in required:
        issue = required["restrict_security_group"]
        return AuditAction(action_type=ActionType.restrict_security_group, target_resource=issue.resource_id)
    if "fix_s3_public_access" in required:
        issue = required["fix_s3_public_access"]
        return AuditAction(action_type=ActionType.fix_s3_public_access, target_resource=issue.resource_id)
    if "encrypt_database" in required:
        issue = required["encrypt_database"]
        return AuditAction(action_type=ActionType.encrypt_database, target_resource=issue.resource_id)

    return AuditAction(action_type=ActionType.scan_resources)


def main() -> int:
    root = Path(__file__).resolve().parent
    required_files = [root / "openenv.yaml", root / "pyproject.toml", root / "Dockerfile"]
    missing = [str(path.name) for path in required_files if not path.exists()]
    if missing:
        print(f"Missing required files: {', '.join(missing)}")
        return 1

    env = CloudAuditEnv()
    scores: dict[str, float] = {}
    for task_id in TASK_ORDER:
        observation = env.reset(task_id=task_id)
        done = False
        step_count = 0
        while not done and step_count < get_task(task_id).max_steps:
            action = build_heuristic_action(observation)
            observation, _, done, _ = env.step(action)
            step_count += 1
        scores[task_id] = env.state().score
        print(f"{task_id}: score={scores[task_id]:.2f}")

    if any(score < 0.5 for score in scores.values()):
        print("Validation failed: at least one task scored below 0.50")
        return 1

    print("Validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
