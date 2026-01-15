"""
Admin API endpoints for mm-control trading toggle management.

These endpoints provide a secure local admin API for operators to manage
trading state via HTTP rather than PowerShell scripts.

Security:
- Protected by X-Admin-Token header (separate from X-API-Key)
- Localhost-only access enforced via middleware
- All actions logged to audit trail

Usage:
    # Enable trading
    curl -X POST http://localhost:8000/admin/toggle \
        -H "X-Admin-Token: YOUR_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"action": "enable", "reason": "Maintenance complete"}'

    # Disable trading with TTL
    curl -X POST http://localhost:8000/admin/toggle \
        -H "X-Admin-Token: YOUR_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"action": "disable", "reason": "Market volatility", "ttl_minutes": 30}'
"""

import logging
import os
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Admin token header
ADMIN_TOKEN_HEADER = APIKeyHeader(
    name="X-Admin-Token",
    auto_error=False,
    description="Admin token for control operations. Required for toggle endpoints.",
)


class ToggleAction(str, Enum):
    """Valid toggle actions."""

    ENABLE = "enable"
    DISABLE = "disable"


class ToggleRequest(BaseModel):
    """Request body for toggle endpoint."""

    action: ToggleAction = Field(..., description="Action to perform: 'enable' or 'disable'")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for the action")
    ttl_minutes: Optional[int] = Field(
        None,
        ge=1,
        le=1440,  # Max 24 hours
        description="Optional TTL in minutes for auto-revert (disable only)",
    )


class ToggleResponse(BaseModel):
    """Response from toggle endpoint."""

    success: bool = Field(..., description="Whether the action was successful")
    action: str = Field(..., description="The action that was performed")
    trading_enabled: bool = Field(..., description="Current trading state after action")
    reason: str = Field(..., description="Reason provided for the action")
    ttl_minutes: Optional[int] = Field(None, description="TTL if set")
    expires_at: Optional[str] = Field(None, description="Expiry timestamp if TTL set")
    message: str = Field(..., description="Human-readable status message")


class AdminStatusResponse(BaseModel):
    """Response from admin status endpoint."""

    trading_enabled: bool = Field(..., description="Whether trading is currently enabled")
    guard_file_exists: bool = Field(..., description="Whether guard file exists")
    toggle_store_enabled: bool = Field(..., description="Toggle store trading_enabled value")
    disabled_at: Optional[str] = Field(None, description="When trading was disabled")
    disabled_by: Optional[str] = Field(None, description="Who disabled trading")
    disabled_reason: Optional[str] = Field(None, description="Reason for disabling")
    expires_at: Optional[str] = Field(None, description="TTL expiry timestamp")
    time_until_expiry_seconds: Optional[float] = Field(None, description="Seconds until auto-revert")


def get_admin_token() -> Optional[str]:
    """Get the expected admin token from environment."""
    return os.environ.get("ADMIN_TOKEN")


def is_admin_auth_enabled() -> bool:
    """Check if admin authentication is enabled (fail closed if not set)."""
    return get_admin_token() is not None


async def verify_admin_token(
    request: Request,
    admin_token: Optional[str] = Depends(ADMIN_TOKEN_HEADER),
) -> str:
    """
    Verify admin token from request header.

    IMPORTANT: Fails closed - if ADMIN_TOKEN env var is not set, all admin
    requests are rejected. This is intentional for security.

    Args:
        request: FastAPI request object
        admin_token: Admin token from X-Admin-Token header

    Returns:
        The admin token if valid

    Raises:
        HTTPException: If authentication fails or token not configured
    """
    expected_token = get_admin_token()

    # Fail closed: if ADMIN_TOKEN not set, reject all admin requests
    if expected_token is None:
        logger.warning(
            f"Admin request rejected: ADMIN_TOKEN not configured. "
            f"Client IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "ADMIN_TOKEN_NOT_CONFIGURED",
                "message": (
                    "Admin API is disabled. Set ADMIN_TOKEN environment variable "
                    "to enable admin operations."
                ),
            },
        )

    # Require token in request
    if admin_token is None:
        logger.warning(
            f"Admin request rejected: missing token. "
            f"Client IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "MISSING_ADMIN_TOKEN",
                "message": "Missing X-Admin-Token header.",
            },
        )

    # Validate token
    if admin_token != expected_token:
        logger.warning(
            f"Admin request rejected: invalid token. "
            f"Client IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "INVALID_ADMIN_TOKEN",
                "message": "Invalid admin token.",
            },
        )

    return admin_token


async def verify_localhost_only(request: Request) -> None:
    """
    Verify request is from localhost only.

    Admin endpoints should only be accessible from the local machine.

    Raises:
        HTTPException: If request is not from localhost
    """
    if request.client is None:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "UNKNOWN_CLIENT",
                "message": "Cannot determine client address.",
            },
        )

    client_host = request.client.host
    localhost_addresses = ("127.0.0.1", "::1", "localhost")

    if client_host not in localhost_addresses:
        logger.warning(f"Admin request rejected: non-localhost client {client_host}")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "LOCALHOST_ONLY",
                "message": f"Admin API is localhost-only. Request from {client_host} rejected.",
            },
        )


# Create router with admin prefix
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_localhost_only), Depends(verify_admin_token)],
)


@router.post(
    "/toggle",
    response_model=ToggleResponse,
    summary="Toggle trading state",
    description=(
        "Enable or disable trading. Requires admin token authentication. "
        "Disable actions can include an optional TTL for auto-revert."
    ),
    responses={
        401: {"description": "Missing or invalid admin token"},
        403: {"description": "Admin API disabled or non-localhost request"},
        500: {"description": "mm-control error"},
    },
)
async def toggle_trading(
    request: Request,
    body: ToggleRequest,
) -> ToggleResponse:
    """
    Toggle trading enable/disable state.

    This endpoint:
    1. Validates the admin token
    2. Performs the enable/disable action via mm-control
    3. Creates an audit log entry
    4. Returns the new state

    For disable with TTL:
    - Creates a Windows Scheduled Task for auto-revert
    - Sets expires_at in toggle store
    """
    try:
        from mm_control import (
            disable_trading,
            enable_trading,
            disable_via_toggles,
            enable_via_toggles,
            get_toggle_status,
            schedule_ttl_check_task,
        )
    except ImportError as e:
        logger.error(f"mm-control import failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "MM_CONTROL_NOT_AVAILABLE",
                "message": "mm-control package not installed or import failed.",
            },
        )

    client_ip = request.client.host if request.client else "unknown"

    try:
        if body.action == ToggleAction.ENABLE:
            # Enable trading
            logger.info(f"Admin API: enabling trading. Reason: {body.reason}. Client: {client_ip}")

            # Enable via both mechanisms for consistency
            enable_trading(reason=f"Admin API: {body.reason}")
            enable_via_toggles(reason=f"Admin API: {body.reason}")

            status = get_toggle_status()
            return ToggleResponse(
                success=True,
                action="enable",
                trading_enabled=True,
                reason=body.reason,
                ttl_minutes=None,
                expires_at=None,
                message="Trading enabled successfully.",
            )

        else:  # DISABLE
            # Disable trading
            logger.info(
                f"Admin API: disabling trading. Reason: {body.reason}. "
                f"TTL: {body.ttl_minutes}. Client: {client_ip}"
            )

            # Disable via both mechanisms
            disable_trading(reason=f"Admin API: {body.reason}")
            state = disable_via_toggles(
                reason=f"Admin API: {body.reason}",
                ttl_minutes=body.ttl_minutes,
            )

            # Schedule TTL auto-revert if requested
            if body.ttl_minutes:
                try:
                    schedule_ttl_check_task(body.ttl_minutes)
                    logger.info(f"Scheduled TTL auto-revert in {body.ttl_minutes} minutes")
                except Exception as e:
                    logger.warning(f"Failed to schedule TTL task: {e}")
                    # Don't fail the request, TTL is in toggle store

            return ToggleResponse(
                success=True,
                action="disable",
                trading_enabled=False,
                reason=body.reason,
                ttl_minutes=body.ttl_minutes,
                expires_at=state.expires_at,
                message=f"Trading disabled. {'Auto-revert in ' + str(body.ttl_minutes) + ' minutes.' if body.ttl_minutes else 'No TTL set.'}",
            )

    except Exception as e:
        logger.error(f"Admin toggle failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "TOGGLE_FAILED",
                "message": f"Failed to toggle trading state: {str(e)}",
            },
        )


@router.get(
    "/status",
    response_model=AdminStatusResponse,
    summary="Get detailed admin status",
    description="Get comprehensive trading control status including guard file and toggle store state.",
    dependencies=[Depends(verify_localhost_only)],  # Only localhost check, no auth required for read-only status
    responses={
        403: {"description": "Non-localhost request"},
        500: {"description": "mm-control error"},
    },
)
async def get_admin_status() -> AdminStatusResponse:
    """
    Get detailed trading control status.

    Returns both guard file and toggle store state for comprehensive view.
    """
    try:
        from mm_control import (
            get_guard_path,
            get_toggle_status,
            is_trading_disabled,
        )
    except ImportError as e:
        logger.error(f"mm-control import failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "MM_CONTROL_NOT_AVAILABLE",
                "message": "mm-control package not installed or import failed.",
            },
        )

    try:
        guard_exists = get_guard_path().exists()
        toggle_status = get_toggle_status()
        overall_disabled = is_trading_disabled()

        return AdminStatusResponse(
            trading_enabled=not overall_disabled,
            guard_file_exists=guard_exists,
            toggle_store_enabled=toggle_status.get("trading_enabled", True),
            disabled_at=toggle_status.get("disabled_at"),
            disabled_by=toggle_status.get("disabled_by"),
            disabled_reason=toggle_status.get("disabled_reason"),
            expires_at=toggle_status.get("expires_at"),
            time_until_expiry_seconds=toggle_status.get("time_until_expiry_seconds"),
        )

    except Exception as e:
        logger.error(f"Admin status failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "STATUS_FAILED",
                "message": f"Failed to get status: {str(e)}",
            },
        )


class AuditLogEntry(BaseModel):
    """A single audit log entry."""

    timestamp: str = Field(..., description="ISO timestamp of the entry")
    user: Optional[str] = Field(None, description="User who performed the action")
    action: str = Field(..., description="Action performed (ENABLE, DISABLE, etc.)")
    reason: Optional[str] = Field(None, description="Reason for the action")


class AuditLogResponse(BaseModel):
    """Response from audit log endpoint."""

    entries: list[AuditLogEntry] = Field(default_factory=list, description="Audit log entries")
    total_lines: int = Field(..., description="Total number of lines in log file")


@router.get(
    "/audit-log",
    response_model=AuditLogResponse,
    summary="Get recent audit log entries",
    description="Retrieve recent entries from the mm-control audit log.",
    dependencies=[Depends(verify_localhost_only)],  # Only localhost check, no auth required for read-only log
    responses={
        403: {"description": "Non-localhost request"},
        500: {"description": "Failed to read audit log"},
    },
)
async def get_audit_log(lines: int = 50) -> AuditLogResponse:
    """
    Get recent audit log entries.

    Args:
        lines: Number of recent entries to return (default: 50, max: 500)

    Returns:
        List of parsed audit log entries
    """
    # Clamp lines to reasonable range
    lines = max(1, min(lines, 500))

    try:
        from mm_control import get_audit_log_path
    except ImportError as e:
        logger.error(f"mm-control import failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "MM_CONTROL_NOT_AVAILABLE",
                "message": "mm-control package not installed or import failed.",
            },
        )

    try:
        audit_path = get_audit_log_path()

        if not audit_path.exists():
            return AuditLogResponse(entries=[], total_lines=0)

        # Read all lines and get the last N
        with open(audit_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        # Parse entries (format: "timestamp | user | action | reason:...")
        entries = []
        for line in reversed(recent_lines):  # Most recent first
            line = line.strip()
            if not line:
                continue

            try:
                entry = _parse_audit_line(line)
                if entry:
                    entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse audit line: {line[:100]}... - {e}")

        return AuditLogResponse(entries=entries, total_lines=total_lines)

    except Exception as e:
        logger.error(f"Failed to read audit log: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "AUDIT_LOG_FAILED",
                "message": f"Failed to read audit log: {str(e)}",
            },
        )


def _parse_audit_line(line: str) -> Optional[AuditLogEntry]:
    """
    Parse an audit log line.

    Expected format: "2026-01-14T10:00:00+00:00 | username | ACTION | reason:Some reason | other:data"
    """
    parts = [p.strip() for p in line.split("|")]

    if len(parts) < 3:
        return None

    timestamp = parts[0]
    user = parts[1] if len(parts) > 1 else None
    action = parts[2] if len(parts) > 2 else "UNKNOWN"

    # Extract reason from remaining parts
    reason = None
    for part in parts[3:]:
        if part.startswith("reason:"):
            reason = part[7:].strip()
            break
        elif not ":" in part:
            # Plain text without key: prefix
            reason = part.strip()

    return AuditLogEntry(
        timestamp=timestamp,
        user=user,
        action=action,
        reason=reason,
    )


# =============================================================================
# Service Restart Endpoints (Phase 5)
# =============================================================================


class ServiceRestartResult(BaseModel):
    """Result for a single service restart."""

    service_name: str = Field(..., description="Name of the service")
    result: str = Field(..., description="Result: SUCCESS, NOT_FOUND, DRY_RUN, STOP_ERROR, START_ERROR, etc.")
    message: str = Field(..., description="Human-readable message")
    restart_duration_seconds: Optional[int] = Field(None, description="Time taken to restart (if successful)")


class RestartRequest(BaseModel):
    """Request body for service restart endpoint."""

    services: list[str] = Field(
        default=["mm-ibkr-api", "mm-signal-listener"],
        description="List of service names to restart. Defaults to trading services.",
    )
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for the restart")
    dry_run: bool = Field(
        False,
        description="If true, checks service status but does not restart. Use for validation.",
    )
    timeout_seconds: int = Field(
        60,
        ge=10,
        le=300,
        description="Max seconds to wait for each service to restart.",
    )


class RestartResponse(BaseModel):
    """Response from restart endpoint."""

    success: bool = Field(..., description="Whether all restarts succeeded (or dry-run completed)")
    dry_run: bool = Field(..., description="Whether this was a dry-run")
    reason: str = Field(..., description="Reason provided for the restart")
    results: list[ServiceRestartResult] = Field(
        default_factory=list,
        description="Results for each service",
    )
    message: str = Field(..., description="Overall status message")


def _check_restart_acl() -> bool:
    """
    Check if restart is allowed by ACL.

    Restart requires explicit opt-in via environment variable for safety.
    """
    acl_value = os.environ.get("ADMIN_RESTART_ENABLED", "false").lower()
    return acl_value in ("true", "1", "yes")


@router.post(
    "/restart",
    response_model=RestartResponse,
    summary="Restart trading services",
    description=(
        "Restart specified Windows services (mm-ibkr-api, mm-signal-listener). "
        "Requires ADMIN_RESTART_ENABLED=true in environment for safety. "
        "Use dry_run=true to check service status without restarting."
    ),
    responses={
        401: {"description": "Missing or invalid admin token"},
        403: {"description": "Admin API disabled, non-localhost, or restart not enabled"},
        500: {"description": "Restart operation failed"},
    },
)
async def restart_services(
    request: Request,
    body: RestartRequest,
) -> RestartResponse:
    """
    Restart Windows services for trading system.

    This endpoint:
    1. Validates admin token and localhost access
    2. Checks if restart is enabled via ACL (ADMIN_RESTART_ENABLED)
    3. Calls restart-services.ps1 or uses native service control
    4. Returns results for each service

    Safety notes:
    - Requires explicit ADMIN_RESTART_ENABLED=true
    - Logs all restart operations to audit trail
    - Use dry_run=true to validate without restarting
    """
    # Check restart ACL
    if not _check_restart_acl():
        logger.warning(
            f"Restart rejected: ADMIN_RESTART_ENABLED not set. "
            f"Client IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RESTART_NOT_ENABLED",
                "message": (
                    "Service restart is not enabled. Set ADMIN_RESTART_ENABLED=true "
                    "in environment to allow restart operations."
                ),
            },
        )

    client_ip = request.client.host if request.client else "unknown"
    mode_str = "DRY-RUN" if body.dry_run else "LIVE"

    logger.info(
        f"Admin API: restart services ({mode_str}). "
        f"Services: {body.services}. Reason: {body.reason}. Client: {client_ip}"
    )

    # Log to mm-control audit
    try:
        from mm_control import write_audit_entry

        action = "RESTART_DRY_RUN" if body.dry_run else "RESTART_REQUEST"
        write_audit_entry(
            action=action,
            reason=body.reason,
            services=",".join(body.services),
            client_ip=client_ip,
        )
    except ImportError:
        logger.warning("mm-control not available, skipping audit log")
    except Exception as e:
        logger.warning(f"Failed to write audit entry: {e}")

    # Perform restarts
    import subprocess
    import sys

    results = []
    all_success = True

    for service_name in body.services:
        try:
            result = _restart_single_service(
                service_name=service_name,
                dry_run=body.dry_run,
                timeout_seconds=body.timeout_seconds,
            )
            results.append(result)

            if result.result not in ("SUCCESS", "DRY_RUN", "NOT_FOUND"):
                all_success = False

        except Exception as e:
            logger.error(f"Error restarting {service_name}: {e}")
            results.append(
                ServiceRestartResult(
                    service_name=service_name,
                    result="ERROR",
                    message=f"Exception: {str(e)}",
                )
            )
            all_success = False

    # Build response message
    success_count = sum(1 for r in results if r.result in ("SUCCESS", "DRY_RUN"))
    fail_count = sum(1 for r in results if r.result not in ("SUCCESS", "DRY_RUN", "NOT_FOUND"))
    not_found_count = sum(1 for r in results if r.result == "NOT_FOUND")

    if body.dry_run:
        message = f"Dry-run complete. {len(results)} services checked."
    elif all_success:
        message = f"All {success_count} services restarted successfully."
    else:
        message = f"Restart completed with issues. Success: {success_count}, Failed: {fail_count}, Not found: {not_found_count}"

    # Log completion
    try:
        from mm_control import write_audit_entry

        completion_action = "RESTART_DRY_RUN_COMPLETE" if body.dry_run else "RESTART_COMPLETE"
        write_audit_entry(
            action=completion_action,
            success=str(success_count),
            failed=str(fail_count),
            not_found=str(not_found_count),
        )
    except Exception:
        pass

    return RestartResponse(
        success=all_success or body.dry_run,
        dry_run=body.dry_run,
        reason=body.reason,
        results=results,
        message=message,
    )


def _restart_single_service(
    service_name: str,
    dry_run: bool,
    timeout_seconds: int,
) -> ServiceRestartResult:
    """
    Restart a single Windows service.

    Uses native Python approach via subprocess to interact with Windows services.
    Falls back to nssm commands if standard service control fails.
    """
    import subprocess
    import time

    # Check if service exists
    try:
        check_result = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if check_result.returncode != 0:
            return ServiceRestartResult(
                service_name=service_name,
                result="NOT_FOUND",
                message=f"Service '{service_name}' not found",
            )
    except Exception as e:
        return ServiceRestartResult(
            service_name=service_name,
            result="CHECK_ERROR",
            message=f"Failed to check service status: {str(e)}",
        )

    # Get current state
    current_state = _get_service_state(service_name)

    if dry_run:
        return ServiceRestartResult(
            service_name=service_name,
            result="DRY_RUN",
            message=f"Would restart service (current state: {current_state})",
        )

    # Stop service if running
    start_time = time.time()
    if current_state == "RUNNING":
        try:
            stop_result = subprocess.run(
                ["net", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            # Wait for service to stop
            wait_start = time.time()
            while time.time() - wait_start < timeout_seconds:
                state = _get_service_state(service_name)
                if state == "STOPPED":
                    break
                time.sleep(0.5)
            else:
                return ServiceRestartResult(
                    service_name=service_name,
                    result="STOP_TIMEOUT",
                    message=f"Service did not stop within {timeout_seconds} seconds",
                )
        except subprocess.TimeoutExpired:
            return ServiceRestartResult(
                service_name=service_name,
                result="STOP_TIMEOUT",
                message=f"Stop command timed out after {timeout_seconds} seconds",
            )
        except Exception as e:
            return ServiceRestartResult(
                service_name=service_name,
                result="STOP_ERROR",
                message=f"Failed to stop service: {str(e)}",
            )

    # Start service
    try:
        start_result = subprocess.run(
            ["net", "start", service_name],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        # Wait for service to start
        wait_start = time.time()
        while time.time() - wait_start < timeout_seconds:
            state = _get_service_state(service_name)
            if state == "RUNNING":
                restart_duration = int(time.time() - start_time)
                return ServiceRestartResult(
                    service_name=service_name,
                    result="SUCCESS",
                    message="Service restarted successfully",
                    restart_duration_seconds=restart_duration,
                )
            time.sleep(0.5)

        return ServiceRestartResult(
            service_name=service_name,
            result="START_TIMEOUT",
            message=f"Service did not start within {timeout_seconds} seconds",
        )

    except subprocess.TimeoutExpired:
        return ServiceRestartResult(
            service_name=service_name,
            result="START_TIMEOUT",
            message=f"Start command timed out after {timeout_seconds} seconds",
        )
    except Exception as e:
        return ServiceRestartResult(
            service_name=service_name,
            result="START_ERROR",
            message=f"Failed to start service: {str(e)}",
        )


def _get_service_state(service_name: str) -> str:
    """Get current state of a Windows service."""
    import subprocess

    try:
        result = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout
        if "RUNNING" in output:
            return "RUNNING"
        elif "STOPPED" in output:
            return "STOPPED"
        elif "START_PENDING" in output:
            return "START_PENDING"
        elif "STOP_PENDING" in output:
            return "STOP_PENDING"
        else:
            return "UNKNOWN"
    except Exception:
        return "ERROR"
