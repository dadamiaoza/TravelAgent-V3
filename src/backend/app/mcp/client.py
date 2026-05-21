"""MCP Client Wrapper — thin isolation layer around langchain_mcp_adapters.

Four entry points (creation / caching / error handling / test double).
Lazy singleton: MCP session established on first get_tools(), not at import time.
"""

import asyncio
import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


class MCPClientWrapper:
    """Lazy-loading MCP client that wraps MultiServerMCPClient.

    On first get_tools(): establishes MCP session, loads tools, caches them.
    On error: returns empty tool list (agent continues with remaining tools).
    set_test_double(): injects mock tools for testing, bypasses real MCP.
    invalidate(): clears cache so next get_tools() reconnects.
    """

    def __init__(self, server_name: str, server_config: dict[str, Any]) -> None:
        self._server_name = server_name
        self._config = server_config
        self._client: MultiServerMCPClient | None = None
        self._tools: list | None = None
        self._test_double: list | None = None
        self._error: str | None = None

    # ── public API ──────────────────────────────────────────────

    def get_tools(self) -> list:
        """Return cached tools, loading them on first call. Never raises."""
        if self._test_double is not None:
            return self._test_double
        if self._tools is not None:
            return self._tools
        try:
            self._tools = asyncio.run(self._load_tools())
            if self._tools:
                logger.info("MCP[%s]: loaded %d tools", self._server_name, len(self._tools))
            else:
                logger.warning("MCP[%s]: connected but server returned 0 tools", self._server_name)
        except Exception:
            logger.exception("MCP[%s]: connection failed, agent will run without these tools", self._server_name)
            self._tools = []
            self._error = "connection_failed"
        return self._tools

    def invalidate(self) -> None:
        """Clear cached tools so next get_tools() reconnects."""
        self._tools = None
        self._error = None

    def set_test_double(self, tools: list) -> None:
        """Inject mock tools. Call with empty list to simulate MCP unavailable."""
        self._test_double = tools

    def clear_test_double(self) -> None:
        """Remove test double, restore real MCP on next get_tools()."""
        self._test_double = None

    # ── properties ──────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._tools is not None and len(self._tools) > 0

    @property
    def last_error(self) -> str | None:
        return self._error

    # ── internal ────────────────────────────────────────────────

    async def _load_tools(self) -> list:
        self._client = MultiServerMCPClient({self._server_name: self._config})
        return await self._client.get_tools(server_name=self._server_name)
