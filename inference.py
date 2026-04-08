from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

from env import ActionType, AuditAction, CloudAuditEnv, TASK_ORDER


def _load_local_env() -> None:
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    env_file = Path(__file__).resolve().parent / ".env"
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


_load_local_env()

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
AUTH_TOKEN = OPENAI_API_KEY or HF_TOKEN
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME") or os.getenv("IMAGE_NAME")
BENCHMARK = os.getenv("BENCHMARK", "CloudAuditEnv")
TASK_NAME = os.getenv("TASK_NAME") or os.getenv("MY_ENV_V4_TASK")
MAX_STEPS_OVERRIDE = int(os.getenv("MAX_STEPS", "0"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "256"))
SUCCESS_SCORE_THRESHOLD = float(os.getenv("SUCCESS_SCORE_THRESHOLD", "0.8"))


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: str | None) -> None:
    error_value = error if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={str(done).lower()} error={error_value}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_text = ",".join(f"{value:.2f}" for value in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_text}",
        flush=True,
    )


def _normalize_json_payload(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()

    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(raw[start : end + 1])
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _heuristic_action(observation: Any) -> AuditAction:
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

    # No issues remaining: perform a final verification scan for hard workflow.
    return AuditAction(action_type=ActionType.scan_resources, notes="Post-remediation verification scan.")


def _selected_tasks() -> list[str]:
    if TASK_NAME:
        return [TASK_NAME]
    return list(TASK_ORDER)


def _llm_action(client: OpenAI, observation: Any, step: int, history: list[str]) -> AuditAction | None:
    observation_payload = observation.model_dump(mode="json") if hasattr(observation, "model_dump") else observation
    user_prompt = (
        f"Step={step}\n"
        f"History={json.dumps(history[-4:], ensure_ascii=True)}\n"
        f"Observation={json.dumps(observation_payload, ensure_ascii=True)}\n"
        "Return exactly one JSON object for this schema: "
        '{"action_type":"scan_resources|fix_s3_public_access|encrypt_database|restrict_security_group|update_iam_policy|noop",'
        '"target_resource":null|"string","notes":null|"string"}'
    )

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cloud security remediation agent. "
                        "Choose one safe, valid remediation action per step and return JSON only."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception:
        return None

    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        return None

    payload = _normalize_json_payload(content)
    if payload is None:
        return None

    try:
        return AuditAction.model_validate(payload)
    except Exception:
        return None


def _action_to_text(action: AuditAction) -> str:
    return json.dumps(action.model_dump(mode="json", exclude_none=True), ensure_ascii=True, separators=(",", ":"))


async def run_task(client: OpenAI | None, task_id: str) -> int:
    env = CloudAuditEnv(task_id=task_id)
    rewards: list[float] = []
    history: list[str] = []
    step_count = 0
    score = 0.0
    success = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        observation = env.reset(task_id=task_id)
        max_steps = MAX_STEPS_OVERRIDE if MAX_STEPS_OVERRIDE > 0 else observation.steps_remaining
        done = False

        for step in range(1, max_steps + 1):
            if done:
                break

            action = _llm_action(client, observation, step, history) if client is not None else None
            if action is None:
                action = _heuristic_action(observation)

            observation, reward, done, info = env.step(action)
            reward_value = reward.value
            error_value = info.get("last_action_error") if isinstance(info, dict) else None

            step_count = step
            rewards.append(reward_value)
            history.append(f"step={step} action={action.action_type.value} reward={reward_value:.2f}")

            log_step(
                step=step,
                action=_action_to_text(action),
                reward=reward_value,
                done=done,
                error=error_value,
            )

        state = env.state()
        score = state.score
        success = score >= SUCCESS_SCORE_THRESHOLD and state.done
    except Exception as exc:
        print(f"Task {task_id} failed: {exc}", file=sys.stderr)
    finally:
        try:
            env.close()
        finally:
            log_end(success=success, steps=step_count, score=score, rewards=rewards)

    return 0 if success else 1


async def main() -> int:
    # Declared for compatibility with submission templates that pass container image names.
    _ = LOCAL_IMAGE_NAME

    client = None
    if AUTH_TOKEN:
        try:
            client = OpenAI(api_key=AUTH_TOKEN, base_url=API_BASE_URL)
        except Exception as exc:
            print(f"OpenAI client initialization failed: {exc}", file=sys.stderr)
            client = None

    status = 0
    for task_id in _selected_tasks():
        result = await run_task(client, task_id)
        status = max(status, result)
    return status


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
