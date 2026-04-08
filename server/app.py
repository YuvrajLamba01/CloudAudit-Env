from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from env import AuditAction, AuditObservation, AuditState, CloudAuditEnv, TASK_ORDER


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str | None = None


class MCPRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: str | None = None
    id: str | int | None = None
    method: str | None = None
    params: dict[str, Any] | None = None


app = FastAPI(
    title="CloudAuditEnv",
    version="1.0.0",
    description="OpenEnv environment for cloud security auditing and misconfiguration remediation.",
)
ENV = CloudAuditEnv()
BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR.parent / "ui"
STATIC_DIR = UI_DIR

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/metadata")
def metadata() -> dict[str, Any]:
    return {
        "name": "CloudAuditEnv",
        "description": "Cloud security audit and remediation simulation.",
        "tags": ["openenv", "cloud-security", "audit", "remediation"],
        "tasks": TASK_ORDER,
        "entrypoint": "server.app:main",
        "mode": "simulation",
    }


@app.get("/schema")
def schema() -> dict[str, Any]:
    return {
        "action": AuditAction.model_json_schema(),
        "observation": AuditObservation.model_json_schema(),
        "state": AuditState.model_json_schema(),
    }


@app.post("/mcp")
def mcp(request: MCPRequest | dict[str, Any]) -> dict[str, Any]:
    payload = request.model_dump() if isinstance(request, MCPRequest) else dict(request)
    return {
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "result": {
            "status": "ok",
            "method": payload.get("method", "unknown"),
        },
    }


@app.post("/reset")
def reset(request: ResetRequest) -> dict[str, Any]:
    try:
        observation = ENV.reset(task_id=request.task_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "observation": observation.model_dump(),
        "state": ENV.state().model_dump(),
    }


@app.post("/step")
def step(action: AuditAction) -> dict[str, Any]:
    try:
        observation, reward, done, info = ENV.step(action)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "observation": observation.model_dump(),
        "reward": reward.model_dump(),
        "done": done,
        "info": info,
    }


@app.get("/state")
def state() -> dict[str, Any]:
    return ENV.state().model_dump()


def main() -> None:
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
