"""
HTTP Client for IBKR REST API.

Provides an async HTTP client for making requests to the REST API layer.
Handles authentication, timeouts, and connection lifecycle.
"""

from typing import Any, Dict, Optional

import httpx

from mcp_server.config import MCPConfig


class IBKRAPIClient:
    """
    Async HTTP client for IBKR REST API.

    Handles:
    - API key authentication via X-API-Key header
    - Configurable timeouts
    - Lazy client initialization
    - Proper cleanup on close
    """

    def __init__(self, config: MCPConfig):
        """
        Initialize the API client.

        Args:
            config: MCP configuration with API URL, key, and timeout
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> Dict[str, str]:
        """Build request headers including API key if configured."""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["X-API-Key"] = self.config.api_key
        return headers

    async def get_client(self) -> httpx.AsyncClient:
        """
        Get or create the async HTTP client.

        Creates a new client on first call or if previous client was closed.

        Returns:
            Configured httpx.AsyncClient instance
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.api_base_url,
                headers=self.headers,
                timeout=httpx.Timeout(self.config.request_timeout),
            )
        return self._client

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        Make a GET request to the REST API.

        Args:
            path: API endpoint path (e.g., "/account/summary")
            params: Optional query parameters

        Returns:
            HTTP response
        """
        client = await self.get_client()
        return await client.get(path, params=params)

    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        Make a POST request to the REST API.

        Args:
            path: API endpoint path (e.g., "/market-data/quote")
            json: Optional JSON body

        Returns:
            HTTP response
        """
        client = await self.get_client()
        return await client.post(path, json=json)

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
