"""
Admin API endpoints for trading control management.

These endpoints provide a secure local admin API for operators to manage
trading state via HTTP rather than PowerShell scripts.

Security:
- Protected by X-Admin-Token header (separate from X-API-Key)
- Localhost-only access enforced via middleware
- All actions logged to audit trail

Usage:
    # Update control.json settings
    curl -X PUT http://localhost:8000/admin/control \
        -H "X-Admin-Token: YOUR_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"reason": "Maintenance complete", "orders_enabled": true}'
"""

import asyncio
import contextvars
import logging
import os
import random
import time
from dataclasses import replace
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from api.dependencies import (
    IBKRClientManager,
    RequestContext,
    get_client_manager,
    get_ibkr_executor,
    get_request_context,
    get_request_timeout,
    log_request,
)
from api.errors import APIError, ErrorCode, map_ibkr_exception
from ibkr_core.config import reset_config
from ibkr_core.control import (
    get_audit_log_path,
    get_control_status,
    load_control,
    validate_control,
    write_audit_entry,
    write_control,
)
from ibkr_core.runtime_config import CONFIG_KEYS, get_config_path, load_config_data, update_config_data

logger = logging.getLogger(__name__)

# Admin token header
ADMIN_TOKEN_HEADER = APIKeyHeader(
    name="X-Admin-Token",
    auto_error=False,
    description="Admin token for control operations.",
)


class AdminStatusResponse(BaseModel):
    """Response from admin status endpoint.

    Includes control.json values for trading control.
    """

    # Primary control.json fields
    trading_mode: str = Field(..., description="Trading mode from control.json: paper or live")
    orders_enabled: bool = Field(..., description="Whether orders are enabled in control.json")
    dry_run: bool = Field(..., description="Dry run setting from control.json")
    effective_dry_run: bool = Field(..., description="Effective dry run (false for live+enabled)")
    live_trading_override_file: Optional[str] = Field(None, description="Override file path")
    override_file_exists: Optional[bool] = Field(None, description="Whether override file exists (for live+enabled)")
    override_file_message: Optional[str] = Field(None, description="Override file validation message")
    is_live_trading_enabled: bool = Field(..., description="True if live+enabled")
    validation_errors: list[str] = Field(default_factory=list, description="Control validation errors")
    control_path: str = Field(..., description="Path to control.json")


class GatewayVerificationResponse(BaseModel):
    """Response from gateway verification endpoint."""

    success: bool = Field(..., description="Whether the gateway verification succeeded")
    message: str = Field(..., description="Human-readable status message")
    verification_mode: str = Field(..., description="Verification mode: direct or pooled")
    account_id: Optional[str] = Field(None, description="Account ID used for verification")
    net_liquidation: Optional[float] = Field(None, description="Net liquidation value from summary")
    currency: Optional[str] = Field(None, description="Account currency")
    summary_timestamp: Optional[str] = Field(None, description="Account summary timestamp (ISO 8601)")
    elapsed_ms: Optional[float] = Field(None, description="Verification duration in milliseconds")
    client_id: Optional[int] = Field(None, description="Client ID used for verification")




class RuntimeConfigResponse(BaseModel):
    """Response with runtime config.json values."""

    config_path: str = Field(..., description="Path to config.json")
    config: Dict[str, Any] = Field(..., description="Runtime config.json values")


class ConfigUpdateRequest(BaseModel):
    """Request to update runtime config.json values."""

    reason: str = Field(..., min_length=1, max_length=500, description="Reason for the update")
    updates: Dict[str, Any] = Field(..., description="Config fields to update")


class ConfigUpdateResponse(BaseModel):
    """Response from config update endpoint."""

    success: bool = Field(..., description="Whether the update succeeded")
    updated_keys: list[str] = Field(default_factory=list, description="Config keys updated")
    restart_required: bool = Field(..., description="Whether a service restart is recommended")
    restart_required_keys: list[str] = Field(
        default_factory=list,
        description="Keys that require restart to fully apply",
    )
    config: Dict[str, Any] = Field(..., description="Updated config.json values")
    message: str = Field(..., description="Status message")


class ControlUpdateRequest(BaseModel):
    """Request to update control.json values."""

    reason: str = Field(..., min_length=1, max_length=500, description="Reason for the update")
    trading_mode: Optional[Literal["paper", "live"]] = Field(
        None,
        description="Trading mode: paper or live",
    )
    orders_enabled: Optional[bool] = Field(
        None,
        description="Master toggle for order placement",
    )
    dry_run: Optional[bool] = Field(
        None,
        description="Dry run mode (ignored when live+enabled)",
    )
    live_trading_override_file: Optional[str] = Field(
        None,
        description="Override file path for live+enabled safety check",
    )


class ControlUpdateResponse(BaseModel):
    """Response from control.json update endpoint."""

    success: bool = Field(..., description="Whether the update succeeded")
    updated_fields: list[str] = Field(default_factory=list, description="Fields updated in control.json")
    status: AdminStatusResponse = Field(..., description="Updated admin status")
    message: str = Field(..., description="Status message")


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


async def _execute_ibkr_admin_operation(
    client_manager: IBKRClientManager,
    operation: callable,
    ctx: RequestContext,
    timeout_s: Optional[float] = None,
    *args,
    **kwargs,
):
    """
    Execute an IBKR operation for admin endpoints with timeout and error mapping.
    """
    if timeout_s is None:
        timeout_s = get_request_timeout()

    try:
        client = await client_manager.get_client()
        loop = asyncio.get_running_loop()
        ctx_vars = contextvars.copy_context()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                get_ibkr_executor(),
                lambda: ctx_vars.run(operation, client, *args, **kwargs),
            ),
            timeout=timeout_s,
        )
        log_request(ctx, status="success")
        return result

    except asyncio.TimeoutError:
        log_request(ctx, status="timeout", error="Request timed out")
        raise APIError(
            ErrorCode.TIMEOUT,
            f"Request timed out after {timeout_s}s",
            status_code=504,
        )
    except APIError as exc:
        log_request(ctx, status="error", error=str(exc))
        raise
    except Exception as exc:
        log_request(ctx, status="error", error=str(exc))
        raise map_ibkr_exception(exc)


def _generate_direct_client_id() -> int:
    """Generate a random high client ID to avoid collisions with pooled clients."""
    rng = random.SystemRandom()
    return rng.randint(7000, 9999)


# Create router with admin prefix
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_localhost_only), Depends(verify_admin_token)],
)


@router.get(
    "/status",
    response_model=AdminStatusResponse,
    summary="Get detailed admin status",
    description="Get comprehensive trading control status from control.json.",
    dependencies=[Depends(verify_localhost_only)],  # Only localhost check, no auth required for read-only status
    responses={
        403: {"description": "Non-localhost request"},
        500: {"description": "Control status error"},
    },
)
async def get_admin_status() -> AdminStatusResponse:
    """
    Get detailed trading control status.

    Returns control.json values for trading control.
    """
    try:
        control_status = get_control_status()
        return AdminStatusResponse(
            trading_mode=control_status["trading_mode"],
            orders_enabled=control_status["orders_enabled"],
            dry_run=control_status["dry_run"],
            effective_dry_run=control_status["effective_dry_run"],
            live_trading_override_file=control_status["live_trading_override_file"],
            override_file_exists=control_status["override_file_exists"],
            override_file_message=control_status.get("override_file_message"),
            is_live_trading_enabled=control_status["is_live_trading_enabled"],
            validation_errors=control_status["validation_errors"],
            control_path=control_status["control_path"],
        )
    except Exception as e:
        logger.error("Admin status failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "STATUS_FAILED",
                "message": f"Failed to get status: {str(e)}",
            },
        )


@router.get(
    "/gateway/verify",
    response_model=GatewayVerificationResponse,
    summary="Verify gateway access via account summary",
    description=(
        "Fetch an account summary from IBKR to verify the Gateway is running "
        "and accessible. Requires admin token and localhost access."
    ),
    responses={
        401: {"description": "Missing or invalid admin token"},
        403: {"description": "Admin API disabled or non-localhost request"},
        500: {"description": "Gateway verification failed"},
        504: {"description": "Gateway verification timed out"},
    },
)
async def verify_gateway_access(
    account_id: Optional[str] = None,
    mode: Literal["direct", "pooled"] = "direct",
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
) -> GatewayVerificationResponse:
    """
    Verify gateway access by retrieving account summary.
    """
    from ibkr_core.account import get_account_summary as ibkr_get_summary
    from ibkr_core.client import IBKRClient

    start_time = time.time()

    mode_value = mode.lower().strip()
    if mode_value not in ("direct", "pooled"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_VERIFY_MODE",
                "message": "mode must be 'direct' or 'pooled'",
            },
        )

    client_id = None

    if mode_value == "direct":
        client_id = _generate_direct_client_id()
        timeout_s = get_request_timeout()
        connect_timeout = int(min(10, max(5, timeout_s)))

        def _direct_summary():
            client = IBKRClient(client_id=client_id)
            try:
                client.connect(timeout=connect_timeout)
                return ibkr_get_summary(client, account_id=account_id)
            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass

        try:
            loop = asyncio.get_running_loop()
            ctx_vars = contextvars.copy_context()
            summary = await asyncio.wait_for(
                loop.run_in_executor(
                    get_ibkr_executor(),
                    lambda: ctx_vars.run(_direct_summary),
                ),
                timeout=timeout_s,
            )
            log_request(ctx, status="success")
        except asyncio.TimeoutError:
            log_request(ctx, status="timeout", error="Request timed out")
            raise APIError(
                ErrorCode.TIMEOUT,
                f"Request timed out after {timeout_s}s",
                status_code=504,
            )
        except APIError:
            log_request(ctx, status="error", error="Gateway verification failed")
            raise
        except Exception as exc:
            log_request(ctx, status="error", error=str(exc))
            raise map_ibkr_exception(exc)
    else:
        def _get_summary(client):
            return ibkr_get_summary(client, account_id=account_id)

        summary = await _execute_ibkr_admin_operation(client_manager, _get_summary, ctx)

    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    return GatewayVerificationResponse(
        success=True,
        message="Gateway verified via account summary.",
        verification_mode=mode_value,
        account_id=summary.accountId,
        net_liquidation=summary.netLiquidation,
        currency=summary.currency,
        summary_timestamp=summary.timestamp.isoformat() if summary.timestamp else None,
        elapsed_ms=elapsed_ms,
        client_id=client_id,
    )


@router.put(
    "/control",
    response_model=ControlUpdateResponse,
    summary="Update control.json settings",
    description=(
        "Update control.json values for trading_mode, orders_enabled, dry_run, "
        "and live_trading_override_file. Requires admin token authentication."
    ),
    responses={
        400: {"description": "Invalid control settings"},
        401: {"description": "Missing or invalid admin token"},
        403: {"description": "Admin API disabled or non-localhost request"},
        500: {"description": "Control update error"},
    },
)
async def update_control_settings(
    request: Request,
    body: ControlUpdateRequest,
) -> ControlUpdateResponse:
    """
    Update control.json settings.

    Applies partial updates to the centralized control.json file and validates
    the resulting configuration before writing.
    """
    current = load_control()
    updated = replace(current)
    updated_fields: list[str] = []

    if body.trading_mode is not None and body.trading_mode != current.trading_mode:
        updated.trading_mode = body.trading_mode
        updated_fields.append("trading_mode")

    if body.orders_enabled is not None and body.orders_enabled != current.orders_enabled:
        updated.orders_enabled = body.orders_enabled
        updated_fields.append("orders_enabled")

    if body.dry_run is not None and body.dry_run != current.dry_run:
        updated.dry_run = body.dry_run
        updated_fields.append("dry_run")

    if body.live_trading_override_file is not None:
        override_value = body.live_trading_override_file.strip()
        override_value = override_value if override_value else None
        if override_value != current.live_trading_override_file:
            updated.live_trading_override_file = override_value
            updated_fields.append("live_trading_override_file")

    if not updated_fields:
        return ControlUpdateResponse(
            success=True,
            updated_fields=[],
            status=await get_admin_status(),
            message="No changes applied.",
        )

    validation_errors = validate_control(updated)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_CONTROL_SETTINGS",
                "message": "Invalid control.json settings.",
                "validation_errors": validation_errors,
            },
        )

    try:
        write_control(updated)
        reset_config()
    except Exception as exc:
        logger.error(f"Failed to write control.json: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "CONTROL_UPDATE_FAILED",
                "message": f"Failed to update control.json: {str(exc)}",
            },
        )

    try:
        write_audit_entry(
            action="CONTROL_UPDATED",
            reason=body.reason,
            updated_fields=",".join(updated_fields),
            client_ip=request.client.host if request.client else "unknown",
        )
    except Exception as exc:
        logger.warning("Failed to write control update audit entry: %s", exc)

    return ControlUpdateResponse(
        success=True,
        updated_fields=updated_fields,
        status=await get_admin_status(),
        message="Control settings updated.",
    )


@router.get(
    "/config",
    response_model=RuntimeConfigResponse,
    summary="Get runtime config.json",
    description="Retrieve the current ProgramData config.json values.",
)
async def get_runtime_config() -> RuntimeConfigResponse:
    config_path = get_config_path()
    config_data = load_config_data(create_if_missing=True)
    return RuntimeConfigResponse(config_path=str(config_path), config=config_data)


@router.put(
    "/config",
    response_model=ConfigUpdateResponse,
    summary="Update runtime config.json",
    description="Update runtime configuration values stored in ProgramData config.json.",
)
async def update_runtime_config_endpoint(
    request: Request,
    body: ConfigUpdateRequest,
) -> ConfigUpdateResponse:
    invalid_keys = [
        key for key in body.updates.keys()
        if key not in CONFIG_KEYS or key == "schema_version"
    ]
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_CONFIG_KEYS",
                "message": f"Unsupported config keys: {', '.join(sorted(invalid_keys))}",
            },
        )

    if not body.updates:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "EMPTY_UPDATE",
                "message": "No config updates provided.",
            },
        )

    updated_config = update_config_data(body.updates)
    reset_config()

    restart_sensitive_keys = {
        "api_bind_host",
        "api_port",
        "ibkr_gateway_host",
        "paper_gateway_port",
        "paper_client_id",
        "live_gateway_port",
        "live_client_id",
        "ibkr_gateway_path",
        "data_storage_dir",
        "log_dir",
        "log_format",
        "log_level",
    }
    updated_keys = sorted(body.updates.keys())
    restart_required_keys = sorted(set(updated_keys).intersection(restart_sensitive_keys))
    restart_required = len(restart_required_keys) > 0

    try:
        write_audit_entry(
            action="CONFIG_UPDATED",
            reason=f"Admin API: {body.reason}",
            details={
                "updated_keys": updated_keys,
                "client": request.client.host if request.client else "unknown",
            },
        )
    except Exception as exc:
        logger.warning("Failed to write config update audit entry: %s", exc)

    message = "Config updated successfully."
    if restart_required:
        message = "Config updated. Restart services to apply changes."

    return ConfigUpdateResponse(
        success=True,
        updated_keys=updated_keys,
        restart_required=restart_required,
        restart_required_keys=restart_required_keys,
        config=updated_config,
        message=message,
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
    description="Retrieve recent entries from the control.json audit log.",
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

    audit_path = get_audit_log_path()

    try:
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

    Restart requires explicit opt-in via config.json for safety.
    """
    from ibkr_core.config import get_config

    return get_config().admin_restart_enabled


@router.post(
    "/restart",
    response_model=RestartResponse,
    summary="Restart trading services",
    description=(
        "Restart specified Windows services (mm-ibkr-api, mm-signal-listener). "
        "Requires admin_restart_enabled=true in config.json for safety. "
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
    2. Checks if restart is enabled via ACL (config.json)
    3. Calls restart-services.ps1 or uses native service control
    4. Returns results for each service

    Safety notes:
    - Requires explicit admin_restart_enabled=true
    - Logs all restart operations to audit trail
    - Use dry_run=true to validate without restarting
    """
    # Check restart ACL
    if not _check_restart_acl():
        logger.warning(
            "Restart rejected: admin_restart_enabled not set in config.json. "
            f"Client IP: {request.client.host if request.client else 'unknown'}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RESTART_NOT_ENABLED",
                "message": (
                    "Service restart is not enabled. Set admin_restart_enabled=true "
                    "in config.json to allow restart operations."
                ),
            },
        )

    client_ip = request.client.host if request.client else "unknown"
    mode_str = "DRY-RUN" if body.dry_run else "LIVE"

    logger.info(
        f"Admin API: restart services ({mode_str}). "
        f"Services: {body.services}. Reason: {body.reason}. Client: {client_ip}"
    )

    try:
        action = "RESTART_DRY_RUN" if body.dry_run else "RESTART_REQUEST"
        write_audit_entry(
            action=action,
            reason=body.reason,
            services=",".join(body.services),
            client_ip=client_ip,
        )
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
