"""Tests for admin API endpoints (Phase 3).

Tests cover:
- Admin token authentication (fail-closed behavior)
- Localhost-only access enforcement
- Toggle request validation
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import HTTPException

from ibkr_core.config import reset_config
from ibkr_core.runtime_config import load_config_data, write_config_data


@pytest.fixture(autouse=True)
def runtime_config_fixture(tmp_path):
    """Ensure config.json is isolated per test."""
    reset_config()
    old_path = os.environ.get("MM_IBKR_CONFIG_PATH")
    config_path = tmp_path / "config.json"
    os.environ["MM_IBKR_CONFIG_PATH"] = str(config_path)
    load_config_data(create_if_missing=True)
    yield
    if old_path is not None:
        os.environ["MM_IBKR_CONFIG_PATH"] = old_path
    else:
        os.environ.pop("MM_IBKR_CONFIG_PATH", None)
    reset_config()


def update_runtime_config(updates):
    """Update config.json with overrides and reset cached config."""
    data = load_config_data()
    data.update(updates)
    write_config_data(data, path=Path(os.environ["MM_IBKR_CONFIG_PATH"]))
    reset_config()


class TestAdminTokenVerification:
    """Tests for admin token authentication logic."""

    def test_get_admin_token_returns_env_value(self):
        """get_admin_token should return ADMIN_TOKEN from env."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "test-token"}):
            from api.admin import get_admin_token
            assert get_admin_token() == "test-token"

    def test_get_admin_token_returns_none_if_not_set(self):
        """get_admin_token should return None if env not set."""
        env = {k: v for k, v in os.environ.items() if k != "ADMIN_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            from api.admin import get_admin_token
            assert get_admin_token() is None

    def test_is_admin_auth_enabled_true_when_token_set(self):
        """is_admin_auth_enabled should return True when token set."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "test-token"}):
            from api.admin import is_admin_auth_enabled
            assert is_admin_auth_enabled() is True

    def test_is_admin_auth_enabled_false_when_token_not_set(self):
        """is_admin_auth_enabled should return False when token not set."""
        env = {k: v for k, v in os.environ.items() if k != "ADMIN_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            from api.admin import is_admin_auth_enabled
            assert is_admin_auth_enabled() is False

    def test_verify_admin_token_rejects_when_not_configured(self):
        """verify_admin_token should reject when ADMIN_TOKEN not set (fail-closed)."""
        env = {k: v for k, v in os.environ.items() if k != "ADMIN_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            from api.admin import verify_admin_token

            mock_request = MagicMock()
            mock_request.client = MagicMock()
            mock_request.client.host = "127.0.0.1"

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    verify_admin_token(mock_request, "any-token")
                )

            assert exc_info.value.status_code == 403
            assert "ADMIN_TOKEN_NOT_CONFIGURED" in exc_info.value.detail["error"]

    def test_verify_admin_token_rejects_missing_token(self):
        """verify_admin_token should reject when token not provided."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "expected-token"}):
            from api.admin import verify_admin_token

            mock_request = MagicMock()
            mock_request.client = MagicMock()
            mock_request.client.host = "127.0.0.1"

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    verify_admin_token(mock_request, None)
                )

            assert exc_info.value.status_code == 401
            assert "MISSING_ADMIN_TOKEN" in exc_info.value.detail["error"]

    def test_verify_admin_token_rejects_invalid_token(self):
        """verify_admin_token should reject invalid token."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "expected-token"}):
            from api.admin import verify_admin_token

            mock_request = MagicMock()
            mock_request.client = MagicMock()
            mock_request.client.host = "127.0.0.1"

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    verify_admin_token(mock_request, "wrong-token")
                )

            assert exc_info.value.status_code == 401
            assert "INVALID_ADMIN_TOKEN" in exc_info.value.detail["error"]

    def test_verify_admin_token_accepts_valid_token(self):
        """verify_admin_token should accept valid token."""
        with patch.dict(os.environ, {"ADMIN_TOKEN": "valid-token"}):
            from api.admin import verify_admin_token

            mock_request = MagicMock()
            mock_request.client = MagicMock()
            mock_request.client.host = "127.0.0.1"

            result = asyncio.get_event_loop().run_until_complete(
                verify_admin_token(mock_request, "valid-token")
            )

            assert result == "valid-token"


class TestLocalhostOnlyVerification:
    """Tests for localhost-only access enforcement."""

    def test_rejects_remote_ipv4(self):
        """Should reject requests from remote IPv4 addresses."""
        from api.admin import verify_localhost_only

        mock_request = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.100"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_localhost_only(mock_request)
            )

        assert exc_info.value.status_code == 403
        assert "LOCALHOST_ONLY" in exc_info.value.detail["error"]

    def test_rejects_remote_ipv6(self):
        """Should reject requests from remote IPv6 addresses."""
        from api.admin import verify_localhost_only

        mock_request = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "2001:db8::1"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_localhost_only(mock_request)
            )

        assert exc_info.value.status_code == 403

    def test_accepts_localhost_127(self):
        """Should accept requests from 127.0.0.1."""
        from api.admin import verify_localhost_only

        mock_request = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        # Should not raise
        asyncio.get_event_loop().run_until_complete(
            verify_localhost_only(mock_request)
        )

    def test_accepts_localhost_ipv6(self):
        """Should accept requests from ::1 (IPv6 localhost)."""
        from api.admin import verify_localhost_only

        mock_request = MagicMock()
        mock_request.client = MagicMock()
        mock_request.client.host = "::1"

        # Should not raise
        asyncio.get_event_loop().run_until_complete(
            verify_localhost_only(mock_request)
        )

    def test_rejects_unknown_client(self):
        """Should reject when client info is unavailable."""
        from api.admin import verify_localhost_only

        mock_request = MagicMock()
        mock_request.client = None

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_localhost_only(mock_request)
            )

        assert exc_info.value.status_code == 403
        assert "UNKNOWN_CLIENT" in exc_info.value.detail["error"]


class TestToggleRequestValidation:
    """Tests for ToggleRequest model validation."""

    def test_valid_enable_request(self):
        """Valid enable request should pass validation."""
        from api.admin import ToggleRequest, ToggleAction

        req = ToggleRequest(action=ToggleAction.ENABLE, reason="Test enable")
        assert req.action == ToggleAction.ENABLE
        assert req.reason == "Test enable"
        assert req.ttl_minutes is None

    def test_valid_disable_request_with_ttl(self):
        """Valid disable request with TTL should pass validation."""
        from api.admin import ToggleRequest, ToggleAction

        req = ToggleRequest(
            action=ToggleAction.DISABLE,
            reason="Test disable",
            ttl_minutes=30,
        )
        assert req.action == ToggleAction.DISABLE
        assert req.ttl_minutes == 30

    def test_ttl_minimum_enforced(self):
        """TTL must be at least 1 minute."""
        from api.admin import ToggleRequest, ToggleAction
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToggleRequest(
                action=ToggleAction.DISABLE,
                reason="Test",
                ttl_minutes=0,
            )

    def test_ttl_maximum_enforced(self):
        """TTL must not exceed 1440 minutes (24 hours)."""
        from api.admin import ToggleRequest, ToggleAction
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToggleRequest(
                action=ToggleAction.DISABLE,
                reason="Test",
                ttl_minutes=1500,
            )

    def test_reason_required(self):
        """Reason is required."""
        from api.admin import ToggleRequest, ToggleAction
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToggleRequest(action=ToggleAction.ENABLE)

    def test_reason_cannot_be_empty(self):
        """Reason cannot be empty string."""
        from api.admin import ToggleRequest, ToggleAction
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ToggleRequest(action=ToggleAction.ENABLE, reason="")


class TestToggleResponse:
    """Tests for ToggleResponse model."""

    def test_response_model_creation(self):
        """ToggleResponse should serialize correctly."""
        from api.admin import ToggleResponse

        resp = ToggleResponse(
            success=True,
            action="enable",
            trading_enabled=True,
            reason="Test",
            ttl_minutes=None,
            expires_at=None,
            message="Trading enabled successfully.",
        )

        assert resp.success is True
        assert resp.action == "enable"
        assert resp.trading_enabled is True

    def test_response_with_ttl(self):
        """ToggleResponse with TTL should include expiry."""
        from api.admin import ToggleResponse

        resp = ToggleResponse(
            success=True,
            action="disable",
            trading_enabled=False,
            reason="Maintenance",
            ttl_minutes=30,
            expires_at="2026-01-14T12:00:00+00:00",
            message="Trading disabled. Auto-revert in 30 minutes.",
        )

        assert resp.ttl_minutes == 30
        assert resp.expires_at == "2026-01-14T12:00:00+00:00"


class TestAdminStatusResponse:
    """Tests for AdminStatusResponse model."""

    def test_status_model_creation(self):
        """AdminStatusResponse should serialize correctly."""
        from api.admin import AdminStatusResponse

        status = AdminStatusResponse(
            trading_enabled=False,
            guard_file_exists=True,
            toggle_store_enabled=False,
            disabled_at="2026-01-14T10:00:00+00:00",
            disabled_by="admin",
            disabled_reason="Testing",
            expires_at="2026-01-14T11:00:00+00:00",
            time_until_expiry_seconds=1800.0,
        )

        assert status.trading_enabled is False
        assert status.guard_file_exists is True
        assert status.disabled_by == "admin"
        assert status.time_until_expiry_seconds == 1800.0

    def test_status_when_enabled(self):
        """AdminStatusResponse for enabled state."""
        from api.admin import AdminStatusResponse

        status = AdminStatusResponse(
            trading_enabled=True,
            guard_file_exists=False,
            toggle_store_enabled=True,
            disabled_at=None,
            disabled_by=None,
            disabled_reason=None,
            expires_at=None,
            time_until_expiry_seconds=None,
        )

        assert status.trading_enabled is True
        assert status.guard_file_exists is False
        assert status.disabled_at is None


class TestAuditLogEntry:
    """Tests for AuditLogEntry model."""

    def test_entry_model_creation(self):
        """AuditLogEntry should serialize correctly."""
        from api.admin import AuditLogEntry

        entry = AuditLogEntry(
            timestamp="2026-01-14T10:00:00+00:00",
            user="admin",
            action="DISABLE",
            reason="Market volatility",
        )

        assert entry.timestamp == "2026-01-14T10:00:00+00:00"
        assert entry.user == "admin"
        assert entry.action == "DISABLE"
        assert entry.reason == "Market volatility"

    def test_entry_optional_fields(self):
        """AuditLogEntry should handle optional fields."""
        from api.admin import AuditLogEntry

        entry = AuditLogEntry(
            timestamp="2026-01-14T10:00:00+00:00",
            action="ENABLE",
        )

        assert entry.user is None
        assert entry.reason is None


class TestAuditLogResponse:
    """Tests for AuditLogResponse model."""

    def test_response_model_creation(self):
        """AuditLogResponse should serialize correctly."""
        from api.admin import AuditLogResponse, AuditLogEntry

        entries = [
            AuditLogEntry(
                timestamp="2026-01-14T10:00:00+00:00",
                user="admin",
                action="DISABLE",
                reason="Test",
            ),
        ]

        response = AuditLogResponse(entries=entries, total_lines=100)

        assert len(response.entries) == 1
        assert response.total_lines == 100

    def test_empty_response(self):
        """AuditLogResponse should handle empty entries."""
        from api.admin import AuditLogResponse

        response = AuditLogResponse(entries=[], total_lines=0)

        assert len(response.entries) == 0
        assert response.total_lines == 0


class TestParseAuditLine:
    """Tests for _parse_audit_line function."""

    def test_parse_full_line(self):
        """Should parse a full audit log line."""
        from api.admin import _parse_audit_line

        line = "2026-01-14T10:00:00+00:00 | admin | DISABLE | reason:Market volatility"
        entry = _parse_audit_line(line)

        assert entry is not None
        assert entry.timestamp == "2026-01-14T10:00:00+00:00"
        assert entry.user == "admin"
        assert entry.action == "DISABLE"
        assert entry.reason == "Market volatility"

    def test_parse_line_without_reason_prefix(self):
        """Should parse line with plain reason (no prefix)."""
        from api.admin import _parse_audit_line

        line = "2026-01-14T10:00:00+00:00 | admin | ENABLE | Trading resumed"
        entry = _parse_audit_line(line)

        assert entry is not None
        assert entry.action == "ENABLE"
        assert entry.reason == "Trading resumed"

    def test_parse_minimal_line(self):
        """Should parse minimal line with just timestamp, user, action."""
        from api.admin import _parse_audit_line

        line = "2026-01-14T10:00:00+00:00 | admin | ENABLE"
        entry = _parse_audit_line(line)

        assert entry is not None
        assert entry.action == "ENABLE"
        assert entry.reason is None

    def test_parse_invalid_line(self):
        """Should return None for invalid lines."""
        from api.admin import _parse_audit_line

        # Too few parts
        entry = _parse_audit_line("just some text")
        assert entry is None

        # Only two parts
        entry = _parse_audit_line("2026-01-14 | admin")
        assert entry is None

    def test_parse_line_with_extra_data(self):
        """Should parse line with additional key:value pairs."""
        from api.admin import _parse_audit_line

        line = "2026-01-14T10:00:00+00:00 | admin | DISABLE | reason:Test | ttl:30m"
        entry = _parse_audit_line(line)

        assert entry is not None
        assert entry.action == "DISABLE"
        assert entry.reason == "Test"


# =============================================================================
# Service Restart Tests (Phase 5)
# =============================================================================


class TestRestartACL:
    """Tests for restart ACL (access control list) check."""

    def test_restart_disabled_by_default(self):
        """Restart should be disabled by default."""
        from api.admin import _check_restart_acl
        assert _check_restart_acl() is False

    def test_restart_disabled_when_false(self):
        """Restart should be disabled when explicitly set to false."""
        update_runtime_config({"admin_restart_enabled": False})
        from api.admin import _check_restart_acl
        assert _check_restart_acl() is False

    def test_restart_enabled_when_true(self):
        """Restart should be enabled when set to true."""
        update_runtime_config({"admin_restart_enabled": True})
        from api.admin import _check_restart_acl
        assert _check_restart_acl() is True

    def test_restart_enabled_with_variations(self):
        """Restart should be enabled with various truthy values."""
        for value in ("true", "TRUE", "True", "1", "yes", "YES"):
            update_runtime_config({"admin_restart_enabled": value})
            from api.admin import _check_restart_acl
            assert _check_restart_acl() is True, f"Failed for value: {value}"


class TestRestartRequest:
    """Tests for RestartRequest model validation."""

    def test_valid_request_default_services(self):
        """Valid request with default services."""
        from api.admin import RestartRequest

        req = RestartRequest(reason="Post-toggle sync")
        assert req.services == ["mm-ibkr-api", "mm-signal-listener"]
        assert req.reason == "Post-toggle sync"
        assert req.dry_run is False
        assert req.timeout_seconds == 60

    def test_valid_request_custom_services(self):
        """Valid request with custom services."""
        from api.admin import RestartRequest

        req = RestartRequest(
            services=["mm-ibkr-api"],
            reason="API update",
        )
        assert req.services == ["mm-ibkr-api"]

    def test_valid_request_dry_run(self):
        """Valid request with dry_run enabled."""
        from api.admin import RestartRequest

        req = RestartRequest(reason="Test run", dry_run=True)
        assert req.dry_run is True

    def test_valid_request_custom_timeout(self):
        """Valid request with custom timeout."""
        from api.admin import RestartRequest

        req = RestartRequest(reason="Test", timeout_seconds=120)
        assert req.timeout_seconds == 120

    def test_timeout_minimum_enforced(self):
        """Timeout must be at least 10 seconds."""
        from api.admin import RestartRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RestartRequest(reason="Test", timeout_seconds=5)

    def test_timeout_maximum_enforced(self):
        """Timeout must not exceed 300 seconds."""
        from api.admin import RestartRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RestartRequest(reason="Test", timeout_seconds=500)

    def test_reason_required(self):
        """Reason is required."""
        from api.admin import RestartRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RestartRequest()

    def test_reason_cannot_be_empty(self):
        """Reason cannot be empty string."""
        from api.admin import RestartRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RestartRequest(reason="")


class TestRestartResponse:
    """Tests for RestartResponse model."""

    def test_response_model_creation(self):
        """RestartResponse should serialize correctly."""
        from api.admin import RestartResponse, ServiceRestartResult

        results = [
            ServiceRestartResult(
                service_name="mm-ibkr-api",
                result="SUCCESS",
                message="Service restarted successfully",
                restart_duration_seconds=5,
            ),
        ]

        resp = RestartResponse(
            success=True,
            dry_run=False,
            reason="Post-toggle sync",
            results=results,
            message="All services restarted successfully.",
        )

        assert resp.success is True
        assert resp.dry_run is False
        assert len(resp.results) == 1

    def test_dry_run_response(self):
        """RestartResponse for dry run."""
        from api.admin import RestartResponse, ServiceRestartResult

        results = [
            ServiceRestartResult(
                service_name="mm-ibkr-api",
                result="DRY_RUN",
                message="Would restart service (current state: RUNNING)",
            ),
        ]

        resp = RestartResponse(
            success=True,
            dry_run=True,
            reason="Test",
            results=results,
            message="Dry-run complete.",
        )

        assert resp.dry_run is True
        assert resp.results[0].result == "DRY_RUN"


class TestServiceRestartResult:
    """Tests for ServiceRestartResult model."""

    def test_success_result(self):
        """ServiceRestartResult for successful restart."""
        from api.admin import ServiceRestartResult

        result = ServiceRestartResult(
            service_name="mm-ibkr-api",
            result="SUCCESS",
            message="Service restarted successfully",
            restart_duration_seconds=8,
        )

        assert result.service_name == "mm-ibkr-api"
        assert result.result == "SUCCESS"
        assert result.restart_duration_seconds == 8

    def test_not_found_result(self):
        """ServiceRestartResult for service not found."""
        from api.admin import ServiceRestartResult

        result = ServiceRestartResult(
            service_name="nonexistent-service",
            result="NOT_FOUND",
            message="Service 'nonexistent-service' not found",
        )

        assert result.result == "NOT_FOUND"
        assert result.restart_duration_seconds is None

    def test_error_result(self):
        """ServiceRestartResult for error."""
        from api.admin import ServiceRestartResult

        result = ServiceRestartResult(
            service_name="mm-ibkr-api",
            result="START_ERROR",
            message="Failed to start: Access denied",
        )

        assert result.result == "START_ERROR"


class TestGetServiceState:
    """Tests for _get_service_state helper function."""

    @patch("subprocess.run")
    def test_running_state(self, mock_run):
        """Should detect running state."""
        from api.admin import _get_service_state

        mock_run.return_value = MagicMock(stdout="STATE: RUNNING", returncode=0)
        state = _get_service_state("test-service")
        assert state == "RUNNING"

    @patch("subprocess.run")
    def test_stopped_state(self, mock_run):
        """Should detect stopped state."""
        from api.admin import _get_service_state

        mock_run.return_value = MagicMock(stdout="STATE: STOPPED", returncode=0)
        state = _get_service_state("test-service")
        assert state == "STOPPED"

    @patch("subprocess.run")
    def test_error_state(self, mock_run):
        """Should return ERROR on exception."""
        from api.admin import _get_service_state

        mock_run.side_effect = Exception("Command failed")
        state = _get_service_state("test-service")
        assert state == "ERROR"


class TestRestartEndpointACLEnforcement:
    """Tests for restart endpoint ACL enforcement."""

    def test_restart_rejected_when_not_enabled(self):
        """Restart should be rejected when admin_restart_enabled is false."""
        update_runtime_config({"admin_restart_enabled": False})

        with patch.dict(os.environ, {"ADMIN_TOKEN": "test-token"}):
            from api.admin import restart_services, RestartRequest

            mock_request = MagicMock()
            mock_request.client = MagicMock()
            mock_request.client.host = "127.0.0.1"

            body = RestartRequest(reason="Test restart")

            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    restart_services(mock_request, body)
                )

            assert exc_info.value.status_code == 403
            assert "RESTART_NOT_ENABLED" in exc_info.value.detail["error"]
