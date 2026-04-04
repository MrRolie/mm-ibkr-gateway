# mm-ibkr-gateway

`mm-ibkr-gateway` is no longer the canonical repo for Interactive Brokers account monitoring and trade execution.

The canonical MCP-first repo is now:

- https://github.com/MrRolie/mm-ibkr-mcp

Use `mm-ibkr-mcp` for:

- account monitoring
- market data and contract resolution
- order preview and submission
- Telegram-gated approvals
- persisted trade intents and execution state

## What happens here next

This repo will remain public and maintained, but its future scope is narrower:

- IB Gateway deployment
- IB Gateway maintenance
- Docker-based gateway runtime support

Until that repurpose lands, treat this repo as legacy and use `mm-ibkr-mcp` for the active broker MCP workflow.
