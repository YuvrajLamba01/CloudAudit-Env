from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env import ActionType, AuditAction, CloudAuditEnv, TASK_ORDER


ROOT = Path(__file__).resolve().parent
RESULT_FILE = ROOT / "baseline_results.json"


def load_env_file() -> None:
    """Load simple KEY=VALUE pairs from .env if present."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def heuristic_action(observation: Any) -> AuditAction:
    if not observation.discovered:
        return AuditAction(action_type=ActionType.scan_resources, notes="Enumerate issues before remediation.")

    remaining = [issue for issue in observation.current_issues if not issue.fixed]
    remaining_by_action = {issue.required_action.value: issue for issue in remaining}

    if "update_iam_policy" in remaining_by_action:
        issue = remaining_by_action["update_iam_policy"]
        return AuditAction(action_type=ActionType.update_iam_policy, target_resource=issue.resource_id)

    if "restrict_security_group" in remaining_by_action:
        issue = remaining_by_action["restrict_security_group"]
        return AuditAction(action_type=ActionType.restrict_security_group, target_resource=issue.resource_id)

    if "fix_s3_public_access" in remaining_by_action:
        issue = remaining_by_action["fix_s3_public_access"]
        return AuditAction(action_type=ActionType.fix_s3_public_access, target_resource=issue.resource_id)

    if "encrypt_database" in remaining_by_action:
        issue = remaining_by_action["encrypt_database"]
        return AuditAction(action_type=ActionType.encrypt_database, target_resource=issue.resource_id)

    return AuditAction(action_type=ActionType.scan_resources, notes="Post-remediation verification scan.")


def run_task(task_id: str) -> dict[str, Any]:
    env = CloudAuditEnv(task_id=task_id)
    observation = env.reset(task_id=task_id)
    rewards: list[float] = []
    steps = 0

    done = False
    while not done and observation.steps_remaining > 0:
        action = heuristic_action(observation)
        observation, reward, done, _ = env.step(action)
        rewards.append(reward.value)
        steps += 1

    state = env.state()
    env.close()

    return {
        "task_id": task_id,
        "score": round(float(state.score), 4),
        "success": bool(state.done and state.score >= 0.8),
        "steps": steps,
        "rewards": [round(float(v), 4) for v in rewards],
    }


def main() -> int:
    load_env_file()
    task_name = os.getenv("TASK_NAME")
    tasks = [task_name] if task_name else list(TASK_ORDER)

    results = [run_task(task_id) for task_id in tasks]
    avg_score = round(sum(item["score"] for item in results) / max(len(results), 1), 4)

    payload = {
        "benchmark": os.getenv("BENCHMARK", "CloudAuditEnv"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "average_score": avg_score,
        "tasks": results,
    }

    RESULT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
