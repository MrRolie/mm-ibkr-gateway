"""
Integration test for IBKR healthcheck.

This test requires a running IBKR Gateway/TWS instance.
"""

import subprocess
import sys

import pytest

from scripts.healthcheck import healthcheck


class TestHealthcheckIntegration:
    """Integration tests for IBKR connection healthcheck."""
    
    @pytest.mark.integration
    def test_healthcheck_success(self):
        """Test that healthcheck succeeds when IBKR Gateway is running."""
        # Try both paper and live modes since only one gateway can be running at a time
        paper_result = None
        live_result = None
        paper_error = None
        live_error = None
        
        try:
            paper_result = healthcheck(mode="paper")
        except Exception as e:
            paper_error = e
        
        try:
            live_result = healthcheck(mode="live")
        except Exception as e:
            live_error = e
        
        # Succeed if at least one mode works
        if paper_result or live_result:
            return
        
        # Both failed - construct error message
        error_msg = "Both PAPER and LIVE gateways failed:\n"
        error_msg += f"  PAPER (port 4002): {paper_error or 'Connection failed'}\n"
        error_msg += f"  LIVE (port 4001): {live_error or 'Connection failed'}"
        pytest.fail(error_msg)
    
    @pytest.mark.integration
    def test_healthcheck_cli(self):
        """Test that healthcheck CLI returns exit code 0 on success."""
        # Try both paper and live modes
        paper_result = None
        live_result = None
        
        try:
            paper_result = subprocess.run(
                [sys.executable, "scripts/healthcheck.py", "paper"],
                capture_output=True,
                text=True,
                timeout=15
            )
        except subprocess.TimeoutExpired:
            paper_result = None
        
        try:
            live_result = subprocess.run(
                [sys.executable, "scripts/healthcheck.py", "live"],
                capture_output=True,
                text=True,
                timeout=15
            )
        except subprocess.TimeoutExpired:
            live_result = None
        
        # Check if at least one succeeded
        if paper_result and paper_result.returncode == 0:
            assert "Connected to IBKR Gateway" in paper_result.stdout
            assert "Server time:" in paper_result.stdout
            return
        
        if live_result and live_result.returncode == 0:
            assert "Connected to IBKR Gateway" in live_result.stdout
            assert "Server time:" in live_result.stdout
            return
        
        # Both failed - construct error message
        error_msg = "Both PAPER and LIVE gateway CLI tests failed:\n"
        if paper_result:
            error_msg += f"  PAPER: exit code {paper_result.returncode}\n{paper_result.stdout[:200]}\n"
        else:
            error_msg += "  PAPER: timed out\n"
        if live_result:
            error_msg += f"  LIVE: exit code {live_result.returncode}\n{live_result.stdout[:200]}"
        else:
            error_msg += "  LIVE: timed out"
        
        pytest.fail(error_msg)
