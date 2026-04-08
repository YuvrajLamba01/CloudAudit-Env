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

```text
project-root/
│
├── env/
│   ├── environment.py        # Core environment (reset, step, state handling)
│   ├── models.py             # Pydantic models (Action, Observation, Reward, State)
│   ├── tasks.py              # Task definitions (easy, medium, hard)
│   └── graders.py            # Deterministic scoring logic [0.0 - 1.0]
│
├── server/
│   └── app.py                # OpenEnv HTTP server + serves frontend
│
├── ui/
│   ├── index.html            # Main frontend entry
│   ├── style.css             # Styling
│   └── app.js                # Frontend logic
│
├── inference.py              # Baseline runner with [START]/[STEP]/[END] logs
├── baseline.py               # Deterministic heuristic baseline
├── baseline_results.json     # Generated baseline results
│
├── .env                      # Local secrets (ignored in git)
├── .env.example              # Environment variable template
│
├── openenv.yaml              # Environment metadata & task catalog
├── Dockerfile                # Container build & runtime setup
│
└── README.md                 # Project documentation
```

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
