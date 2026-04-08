---
title: CloudAuditEnv
emoji: ☁️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
tags:
  - openenv
  - cloud-security
  - audit
---

# CloudAuditEnv

CloudAuditEnv is a production-ready OpenEnv simulation for cloud security auditing. The agent inspects resources, discovers misconfigurations, applies remediations, and is scored on correctness and efficiency.

## Real-World Use Case

Security and platform teams routinely detect and fix issues such as:

- Public S3 buckets
- Overly permissive IAM policies
- Unencrypted databases
- Open security groups

CloudAuditEnv turns this workflow into a deterministic environment for benchmarking and training autonomous remediation agents.

## Project Structure

- env/environment.py: core environment (`reset`, `step`, `state`)
- env/models.py: typed Pydantic models for action, observation, reward, and state
- env/tasks.py: task definitions (easy, medium, hard)
- env/graders.py: deterministic scoring in [0.0, 1.0]
- inference.py: baseline runner with strict `[START]/[STEP]/[END]` logs
- baseline.py: deterministic local heuristic baseline runner
- baseline_results.json: generated baseline score artifact
- server/app.py: HTTP OpenEnv runtime endpoints
- ui/: frontend files (`index.html`, `style.css`, `app.js`)
- server/app.py serves the frontend root and static assets from `ui/`
- .env / .env.example: local secret and runtime configuration template
- openenv.yaml: environment metadata and task catalog
- Dockerfile: container build and runtime

## Action Space

AuditAction.action_type supports:

- scan_resources
- fix_s3_public_access
- encrypt_database
- restrict_security_group
- update_iam_policy
- noop (penalized safety action)

## Observation Space

AuditObservation includes:

- current_issues: discovered cloud issues and fix status
- resource_state: security posture flags for S3, IAM, DB, and SG
- previous_actions: recent action log entries
- progress_score: normalized grade [0.0, 1.0]
- steps_remaining

## Tasks

1. easy_public_s3 (easy)
- Initial issue: public S3 bucket.
- Goal: scan and block public access.

2. medium_network_data (medium)
- Initial issues: unencrypted database and open security group.
- Goal: discover and remediate both.

3. hard_full_stack (hard)
- Initial issues: public S3, weak IAM, open SG, unencrypted DB.
- Interdependencies: DB encryption requires IAM hardening and network lockdown first.
- Workflow requirement: after fixes, run a final verification scan to close the incident.

## Reward and Grading

Per-step rewards and final score are deterministic and bounded [0.0, 1.0]:

- Partial credit for fixing issues
- Penalties for invalid/repeated/noop actions
- Completion bonus when all issues are fixed
- Efficiency component based on fixes per step
- Workflow component that rewards discovery + verification behavior on the hard task

Grader composition (env/graders.py):

- 55% issue completion
- 20% correctness (penalizes invalid/repeated/workflow-violating actions)
- 15% efficiency
- 10% workflow quality (scan and post-fix verification)
- +0.10 completion bonus (capped at 1.0)

## Setup

```bash
pip install -e .
openenv validate
```

For local secrets, create `.env` from `.env.example` and set `OPENAI_API_KEY` or `HF_TOKEN`.

Alternative install path (common in Spaces CI):

```bash
pip install -r requirements.txt
openenv validate
```

## Run Locally

```bash
python inference.py
```

Generate/update local baseline results:

```bash
python baseline.py
```

Optional environment variables:

- API_BASE_URL
- MODEL_NAME
- OPENAI_API_KEY
- HF_TOKEN
- BENCHMARK
- MAX_STEPS
- SUCCESS_SCORE_THRESHOLD

Credential precedence in `inference.py`:

- `OPENAI_API_KEY` (primary)
- `HF_TOKEN` (fallback)

## Docker

```bash
docker build -t cloudauditenv .
docker run --rm -p 7860:7860 cloudauditenv
```

The container includes `ui/` and serves frontend routes at `/` and `/ui/`, with static assets mounted at `/static`.

## Submission Checklist

- `openenv validate` passes locally.
- `Dockerfile` builds without timeout-heavy system package installs.
- `inference.py` exists at repository root and prints strict `[START]`, `[STEP]`, `[END]` lines.
- `openenv.yaml` includes task metadata and docker runtime config.
- Server exposes required endpoints: `/reset`, `/step`, `/state`.
- Optional validator-friendly endpoints are present: `/health`, `/metadata`, `/schema`, `/mcp`.

## Example Baseline Scores (Heuristic Fallback)

- easy_public_s3: 0.95
- medium_network_data: 0.96
- hard_full_stack: 0.95
