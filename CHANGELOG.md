# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- CLI interface with healthcheck, demo, and start-api commands
- Interactive demo mode showcasing market data and account status
- Comprehensive OSS documentation (CONTRIBUTING, SECURITY, CHANGELOG)
- GitHub issue templates for bugs and features
- Safety checklist for live trading enablement

## [0.1.0] - 2024-12-26

### Added

- IBKR Gateway integration with ib_insync
- Market data fetching (quotes, historical bars)
- Account status queries (summary, positions, P&L)
- Order management (preview, place, cancel, status)
- Advanced order types (trailing stops, brackets, MOC/OPG)
- FastAPI REST interface
- MCP server for Claude Desktop integration
- Docker support with docker-compose
- Comprehensive test suite (100+ tests with unit and integration tests)
- Safety features (paper mode default, orders disabled default)
- Jupyter notebooks for interactive exploration
- Complete API documentation

### Security

- Paper trading mode by default
- Order placement disabled by default (`ORDERS_ENABLED=false`)
- Dual-toggle protection for live trading
- Live trading override file requirement
- SIMULATED status when orders are disabled

[Unreleased]: https://github.com/MrRolie/mm-ibkr-gateway/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MrRolie/mm-ibkr-gateway/releases/tag/v0.1.0
