from datetime import datetime, timezone
import os
import subprocess

from agent.state import DiagnosisState

LOW_RISK_ACTIONS = {
    "flush_cache",
}

HIGH_RISK_ACTIONS = {
    "restart_service",
    "scale_out",
    "rollback_deploy",
}

ALLOWED_ACTIONS = LOW_RISK_ACTIONS | HIGH_RISK_ACTIONS | {"none"}
SERVICE_NAME = "aiops-app"
DRY_RUN = os.getenv("AIOPS_DRY_RUN", "true").strip().lower() not in {"false", "0"}
SCALABLE_ROOT_CAUSES = {"process_cpu_rate", "app_p95_latency_seconds"}
ROLLBACK_ROOT_CAUSES = {
    "app_p95_latency_seconds",
    "app_error_rate",
    "app_availability",
}


def finalize_diagnosis(state: DiagnosisState) -> DiagnosisState:
    action = state["remediation_action"]
    if action is None:
        action = "none"
    elif action not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported remediation action: {action}")

    if state["needs_more_evidence"]:
        action = "none"

    root_metric = state["diagnosed_root_cause"]

    if action == "scale_out" and root_metric not in SCALABLE_ROOT_CAUSES:
        action = "none"

    if action == "rollback_deploy":
        has_recent_deploy = any(
            evidence.get("source") == "deploy_history"
            and evidence.get("count", 0) > 0
            for evidence in state.get("evidence_gathered", [])
        )
        if root_metric not in ROLLBACK_ROOT_CAUSES or not has_recent_deploy:
            action = "none"

    # Safety guard: Redis latency alone is not enough for cache flush
    if action == "flush_cache" and root_metric == "redis_average_latency_seconds":
        has_cache_error = any(
            e.get("metric") == "cache_error_rate"
            for e in state.get("evidence_gathered", [])
        )
        if not has_cache_error:
            action = "none"

    state["remediation_action"] = action

    state["requires_approval"] = (action in HIGH_RISK_ACTIONS)
    state["approval_status"] = ("pending" if state["requires_approval"] else "approved")

    return state


def execute_remediation(state: DiagnosisState) -> DiagnosisState:
    action = state["remediation_action"]
    if action is None or action not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported remediation action: {action}")

    timestamp = datetime.now(timezone.utc).isoformat()

    if DRY_RUN:
        state["remediation_result"] = {
            "action": action,
            "status": "dry_run",
            "timestamp": timestamp,
        }
        return state

    if action == "none":
        state["remediation_result"] = {
            "action": "none",
            "status": "skipped",
            "timestamp": timestamp,
        }
        return state

    commands = {
        "restart_service": (["docker", "compose", "restart", SERVICE_NAME], 30),
        "flush_cache": (
            ["docker", "compose", "exec", "-T", "redis", "redis-cli", "FLUSHALL"],
            15,
        ),
        "scale_out": (["bash", "scripts/scale-out-compose.sh"], 120),
        "rollback_deploy": (["bash", "scripts/rollback-compose.sh"], 120),
    }
    command, timeout = commands[action]
    try:
        subprocess.run(command, check=True, timeout=timeout)
        status = "executed"
    except (OSError, subprocess.SubprocessError) as error:
        status = f"failed: {error}"

    state["remediation_result"] = {
        "action": action,
        "status": status,
        "timestamp": timestamp,
    }

    return state


def remediation_router(state: DiagnosisState) -> str:
    action = state["remediation_action"]

    if action == "none":
        return "finish"

    if state["requires_approval"]:
        return "approval"

    return "execute"


def route_after_approval(state: DiagnosisState) -> str:
    if state["approval_status"] == "approved":
        return "execute_remediation"

    return "reject_remediation"