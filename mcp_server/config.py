"""
MCP Server Configuration.

Loads configuration from environment variables for the MCP server.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class MCPConfig:
    """MCP Server configuration."""

    api_base_url: str = "http://localhost:8000"
    api_key: Optional[str] = None
    request_timeout: float = 60.0


def get_mcp_config() -> MCPConfig:
    """
    Load MCP configuration from environment variables.

    Environment Variables:
        IBKR_API_URL: Base URL of the REST API (default: http://localhost:8000)
        API_KEY: Optional API key for X-API-Key header
        MCP_REQUEST_TIMEOUT: Request timeout in seconds (default: 60)

    Returns:
        MCPConfig instance with loaded values
    """
    timeout_str = os.environ.get("MCP_REQUEST_TIMEOUT", "60.0")
    try:
        timeout = float(timeout_str)
    except (ValueError, TypeError):
        timeout = 60.0

    return MCPConfig(
        api_base_url=os.environ.get("IBKR_API_URL", "http://localhost:8000"),
        api_key=os.environ.get("API_KEY"),
        request_timeout=timeout,
    )
