# IBKR Gateway Demo Notebooks

Interactive Jupyter notebooks demonstrating the IBKR Gateway functionality.

## Prerequisites

- IBKR Gateway or TWS running in paper trading mode
- Connection: `127.0.0.1:4002` (default paper trading port)
- Python environment with project dependencies installed

## Notebooks

### [01_contract_resolution.ipynb](01_contract_resolution.ipynb)
**Phase 1: Contract Resolution**

Demonstrates:
- IBKRClient connection management
- Contract resolution for STK, ETF, FUT, IND
- Futures front-month auto-resolution
- Contract caching and statistics
- Batch contract resolution
- Error handling

### [02_market_data.ipynb](02_market_data.ipynb)
**Phase 2: Market Data**

Demonstrates:
- Snapshot quotes (single and batch)
- Historical bar data (daily and intraday)
- Input normalization (bar sizes, durations)
- Data visualization (optional, requires matplotlib)
- Error handling

### [03_account_status.ipynb](03_account_status.ipynb)

**Phase 3: Account Status**

Demonstrates:
- Account summary (NLV, cash, buying power, margin)
- Portfolio positions with market values and P&L
- Account-level and per-symbol P&L breakdown
- Multi-account support
- Combined status retrieval
- Practical portfolio dashboard example
- Error handling

## Running the Notebooks

1. Start IBKR Gateway/TWS in paper trading mode

2. Navigate to the notebooks directory:
   ```bash
   cd notebooks
   ```

3. Start Jupyter:
   ```bash
   jupyter notebook
   ```
   or
   ```bash
   jupyter lab
   ```

4. Open and run the notebooks in order

## Notes

- **Market Data Permissions**: Paper trading accounts may have limited real-time data. Some quote features may return permission errors or delayed data.
- **Historical Data**: Historical bar data typically works without additional subscriptions.
- **Connection**: Each notebook manages its own connection. Remember to run disconnect cells before closing.
