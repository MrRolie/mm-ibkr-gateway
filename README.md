# IBKR Integration + MCP Tool Server (Work in Progress)

A complete, modular integration of Interactive Brokers (IBKR) with a natural-language interface via an MCP tool server.

## Quick Start

### Prerequisites

- Python 3.10+
- Running IBKR Gateway or TWS (Paper account recommended)
- `pip`, `poetry`, or `uv` for dependency management

### Setup

1. Clone the repository and navigate to the root:

```bash
cd mm-ibkr-gateway
```

2. Install dependencies:

```bash
pip install -r requirements.txt
# or
poetry install
```

3. Create a `.env` file (see `.env.example`):

```bash
cp .env.example .env
```

4. Configure for your environment:

```
IBKR_GATEWAY_HOST=127.0.0.1
IBKR_GATEWAY_PORT=4001
TRADING_MODE=paper
ORDERS_ENABLED=false
```

5. Run the healthcheck to verify IBKR connection:

```bash
python -m ibkr_core.healthcheck
```

## Project Structure

- **`ibkr_core/`** – Core IBKR integration logic
  - `client.py` – Connection wrapper
  - `contracts.py` – Contract resolution
  - `market_data.py` – Quote and historical bar fetching
  - `account.py` – Account status and positions
  - `orders.py` – Order placement and management
  - `models.py` – Pydantic models matching schema

- **`api/`** – FastAPI REST layer
  - `server.py` – Endpoint definitions
  - `schemas.py` – HTTP request/response models

- **`mcp_server/`** – MCP tool server
  - `main.py` – Tool definitions and registration

- **`nl/`** – Natural language / agent layer
  - `agent.py` – LLM interaction and tool execution
  - `agent_prompts.md` – System prompts and guidelines

- **`tests/`** – Unit and integration tests
  - `fixtures/` – Sample JSON payloads

- **`.context/`** – Design and specification documents
  - `PHASE_PLAN.md` – Full implementation roadmap
  - `SCHEMAS.md` – JSON Schema definitions (source of truth)
  - `ARCH_NOTES.md` – Architecture decisions
  - `TODO_BACKLOG.md` – Tracked TODOs and technical debt

## Running Tests

Run all tests:

```bash
pytest
```

Run specific test categories:

```bash
# Unit tests only
pytest tests/test_config.py tests/test_models.py -v

# Integration tests (requires running IBKR Gateway)
pytest tests/test_healthcheck.py -v
```

Run with coverage:

```bash
pytest --cov=ibkr_core --cov=api --cov=mcp_server
```

### Test Results (Phase 0)

✅ **43 tests passing**
- 17 config validation tests
- 24 Pydantic model tests  
- 2 integration tests with live IBKR Gateway

All Phase 0 requirements complete and verified.

## Key Design Decisions

1. **Safety-First**: Paper trading is the default. Live trading requires explicit env var + flag.
2. **Schema-Driven**: All data models match `.context/SCHEMAS.md` exactly.
3. **Pydantic Models**: Strong typing via Pydantic for IDE support and runtime validation.
4. **Thin MCP Layer**: MCP tools are thin wrappers around HTTP API calls.
5. **Three Main Use Cases**:
   - **Fetch data**: Market quotes, historical bars
   - **Fetch account status**: Positions, balances, P&L
   - **Place orders**: With preview and confirmation flow

## Phases

See [`.context/PHASE_PLAN.md`](.context/PHASE_PLAN.md) for the complete multi-phase implementation roadmap.

### Current Phase: Phase 0 ✅ COMPLETE

**Phase 0 – Repo, environment, and safety rails**

All requirements implemented and tested:

- ✅ Clean repo structure with all modules
- ✅ Configuration management with `.env` support
- ✅ Safety rails: `TRADING_MODE` and `ORDERS_ENABLED` validation
- ✅ Live trading override requirement
- ✅ All Pydantic models matching `.context/SCHEMAS.md`
- ✅ Working healthcheck against IBKR Gateway (port 4002)
- ✅ 43 passing tests (unit + integration)

**Verified working with IBKR Gateway:**
- Connected to paper account (DUM096342)
- Server time retrieved successfully
- All safety checks operational

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IBKR_GATEWAY_HOST` | `127.0.0.1` | IBKR Gateway hostname |
| `IBKR_GATEWAY_PORT` | `4001` | IBKR Gateway port |
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `ORDERS_ENABLED` | `false` | Enable order placement |
| `API_PORT` | `8000` | FastAPI server port |
| `LOG_LEVEL` | `INFO` | Logging level |

