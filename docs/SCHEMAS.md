# IBKR Core API Schemas

All schemas in canonical JSON Schema format (draft 2020-12).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/ibkr-core.json",
  "title": "IBKR Core API Schemas",
  "type": "object",
  "description": "Root schema holding reusable IBKR-related definitions.",
  "$defs": {
    "SymbolSpec": {
      "type": "object",
      "description": "Logical description of an instrument to be resolved into an IBKR contract.",
      "properties": {
        "symbol": {
          "type": "string",
          "description": "Base symbol or ticker, e.g. 'AAPL', 'MES', 'SPX'."
        },
        "securityType": {
          "type": "string",
          "description": "IBKR security type code.",
          "enum": ["STK", "ETF", "FUT", "OPT", "IND", "CASH", "CFD", "BOND", "FUND", "CRYPTO"]
        },
        "exchange": {
          "type": "string",
          "description": "Preferred exchange or routing, e.g. 'SMART', 'GLOBEX'.",
          "nullable": true
        },
        "currency": {
          "type": "string",
          "description": "Currency code, e.g. 'USD'.",
          "nullable": true
        },
        "expiry": {
          "type": "string",
          "description": "Contract expiry in YYYY-MM-DD format for derivatives.",
          "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
          "nullable": true
        },
        "strike": {
          "type": "number",
          "description": "Strike price for options.",
          "minimum": 0,
          "nullable": true
        },
        "right": {
          "type": "string",
          "description": "Option right: Call or Put.",
          "enum": ["C", "P"],
          "nullable": true
        },
        "multiplier": {
          "type": "string",
          "description": "Contract multiplier as string (IBKR-style).",
          "nullable": true
        }
      },
      "required": ["symbol", "securityType"],
      "additionalProperties": false
    },

    "Quote": {
      "type": "object",
      "description": "Snapshot of current market data for a single instrument.",
      "properties": {
        "symbol": {
          "type": "string",
          "description": "Logical symbol identifier used in the request, e.g. 'MES'."
        },
        "conId": {
          "type": "integer",
          "description": "IBKR contract identifier."
        },
        "bid": {
          "type": "number",
          "description": "Best bid price.",
          "minimum": 0
        },
        "ask": {
          "type": "number",
          "description": "Best ask price.",
          "minimum": 0
        },
        "last": {
          "type": "number",
          "description": "Last traded price.",
          "minimum": 0
        },
        "bidSize": {
          "type": "number",
          "description": "Bid size in contracts or shares.",
          "minimum": 0
        },
        "askSize": {
          "type": "number",
          "description": "Ask size in contracts or shares.",
          "minimum": 0
        },
        "lastSize": {
          "type": "number",
          "description": "Last traded size.",
          "minimum": 0
        },
        "volume": {
          "type": "number",
          "description": "Session volume.",
          "minimum": 0
        },
        "timestamp": {
          "type": "string",
          "description": "Timestamp of the quote in ISO 8601 format.",
          "format": "date-time"
        },
        "source": {
          "type": "string",
          "description": "Source or feed identifier, e.g. 'IBKR_REALTIME', 'IBKR_DELAYED'."
        }
      },
      "required": ["symbol", "conId", "timestamp", "source"],
      "additionalProperties": false
    },

    "Bar": {
      "type": "object",
      "description": "Single OHLCV bar of historical or intraday data.",
      "properties": {
        "symbol": {
          "type": "string",
          "description": "Logical symbol identifier."
        },
        "time": {
          "type": "string",
          "description": "Bar timestamp in ISO 8601 format.",
          "format": "date-time"
        },
        "open": {
          "type": "number",
          "description": "Open price.",
          "minimum": 0
        },
        "high": {
          "type": "number",
          "description": "High price.",
          "minimum": 0
        },
        "low": {
          "type": "number",
          "description": "Low price.",
          "minimum": 0
        },
        "close": {
          "type": "number",
          "description": "Close price.",
          "minimum": 0
        },
        "volume": {
          "type": "number",
          "description": "Traded volume in this bar.",
          "minimum": 0
        },
        "barSize": {
          "type": "string",
          "description": "Bar size as human string, e.g. '1 min', '5 mins', '1 day'."
        },
        "source": {
          "type": "string",
          "description": "Data source, e.g. 'IBKR_HISTORICAL'."
        }
      },
      "required": ["symbol", "time", "open", "high", "low", "close", "volume", "barSize", "source"],
      "additionalProperties": false
    },

    "AccountSummary": {
      "type": "object",
      "description": "High-level snapshot of account status.",
      "properties": {
        "accountId": {
          "type": "string",
          "description": "IBKR account identifier."
        },
        "currency": {
          "type": "string",
          "description": "Base reporting currency, e.g. 'USD'."
        },
        "netLiquidation": {
          "type": "number",
          "description": "Net liquidation value in base currency.",
          "minimum": 0
        },
        "cash": {
          "type": "number",
          "description": "Cash balance in base currency.",
          "minimum": 0
        },
        "buyingPower": {
          "type": "number",
          "description": "Available buying power in base currency.",
          "minimum": 0
        },
        "marginExcess": {
          "type": "number",
          "description": "Margin excess or deficit (can be negative)."
        },
        "maintenanceMargin": {
          "type": "number",
          "description": "Current maintenance margin requirement.",
          "minimum": 0
        },
        "initialMargin": {
          "type": "number",
          "description": "Current initial margin requirement.",
          "minimum": 0
        },
        "timestamp": {
          "type": "string",
          "description": "Timestamp when the snapshot was taken, ISO 8601.",
          "format": "date-time"
        }
      },
      "required": ["accountId", "currency", "netLiquidation", "timestamp"],
      "additionalProperties": false
    },

    "Position": {
      "type": "object",
      "description": "Single open or recently closed position in the portfolio.",
      "properties": {
        "accountId": {
          "type": "string",
          "description": "IBKR account identifier."
        },
        "symbol": {
          "type": "string",
          "description": "Logical symbol, e.g. 'MES', 'AAPL'."
        },
        "conId": {
          "type": "integer",
          "description": "IBKR contract identifier."
        },
        "assetClass": {
          "type": "string",
          "description": "Instrument class.",
          "enum": ["STK", "ETF", "FUT", "OPT", "FX", "CFD", "IND", "BOND", "FUND", "CRYPTO"]
        },
        "currency": {
          "type": "string",
          "description": "Trading currency, e.g. 'USD'."
        },
        "quantity": {
          "type": "number",
          "description": "Position size (positive for long, negative for short)."
        },
        "avgPrice": {
          "type": "number",
          "description": "Average cost price.",
          "minimum": 0
        },
        "marketPrice": {
          "type": "number",
          "description": "Current market price.",
          "minimum": 0
        },
        "marketValue": {
          "type": "number",
          "description": "Current market value.",
          "minimum": 0
        },
        "unrealizedPnl": {
          "type": "number",
          "description": "Unrealized P&L for this position."
        },
        "realizedPnl": {
          "type": "number",
          "description": "Cumulative realized P&L for this position."
        }
      },
      "required": [
        "accountId",
        "symbol",
        "conId",
        "assetClass",
        "currency",
        "quantity",
        "avgPrice",
        "marketPrice",
        "marketValue",
        "unrealizedPnl",
        "realizedPnl"
      ],
      "additionalProperties": false
    },

    "PnlDetail": {
      "type": "object",
      "description": "Detailed P&L breakdown for a symbol or contract.",
      "properties": {
        "symbol": {
          "type": "string",
          "description": "Symbol associated with this P&L bucket."
        },
        "conId": {
          "type": "integer",
          "description": "IBKR contract identifier.",
          "nullable": true
        },
        "currency": {
          "type": "string",
          "description": "Currency for these P&L values."
        },
        "realized": {
          "type": "number",
          "description": "Total realized P&L."
        },
        "unrealized": {
          "type": "number",
          "description": "Total unrealized P&L."
        },
        "realizedToday": {
          "type": "number",
          "description": "Realized P&L for the current session/timeframe.",
          "nullable": true
        },
        "unrealizedToday": {
          "type": "number",
          "description": "Unrealized P&L change for the current session/timeframe.",
          "nullable": true
        },
        "basis": {
          "type": "number",
          "description": "Cost basis if available.",
          "nullable": true
        }
      },
      "required": ["symbol", "currency", "realized", "unrealized"],
      "additionalProperties": false
    },

    "AccountPnl": {
      "type": "object",
      "description": "Aggregated account-level P&L.",
      "properties": {
        "accountId": {
          "type": "string",
          "description": "IBKR account identifier."
        },
        "currency": {
          "type": "string",
          "description": "Reporting currency."
        },
        "timeframe": {
          "type": "string",
          "description": "Requested timeframe, e.g. 'INTRADAY', '1D', 'MTD', 'YTD'."
        },
        "realized": {
          "type": "number",
          "description": "Total realized P&L in this timeframe."
        },
        "unrealized": {
          "type": "number",
          "description": "Current unrealized P&L."
        },
        "bySymbol": {
          "type": "object",
          "description": "Map of symbol → PnlDetail.",
          "additionalProperties": {
            "$ref": "#/$defs/PnlDetail"
          }
        },
        "timestamp": {
          "type": "string",
          "description": "Timestamp of this P&L snapshot, ISO 8601.",
          "format": "date-time"
        }
      },
      "required": ["accountId", "currency", "timeframe", "realized", "unrealized", "timestamp"],
      "additionalProperties": false
    },

    "OrderSpec": {
      "type": "object",
      "description": "Client-side specification of an order to be placed.",
      "properties": {
        "accountId": {
          "type": "string",
          "description": "Target account for the order.",
          "nullable": true
        },
        "instrument": {
          "$ref": "#/$defs/SymbolSpec",
          "description": "Instrument to trade."
        },
        "side": {
          "type": "string",
          "description": "Order side.",
          "enum": ["BUY", "SELL"]
        },
        "quantity": {
          "type": "number",
          "description": "Absolute quantity (units, shares, contracts). Must be positive.",
          "exclusiveMinimum": 0
        },
        "orderType": {
          "type": "string",
          "description": "Order type.",
          "enum": ["MKT", "LMT", "STP", "STP_LMT"]
        },
        "limitPrice": {
          "type": "number",
          "description": "Limit price, required for LMT and STP_LMT.",
          "minimum": 0,
          "nullable": true
        },
        "stopPrice": {
          "type": "number",
          "description": "Stop trigger price, required for STP and STP_LMT.",
          "minimum": 0,
          "nullable": true
        },
        "tif": {
          "type": "string",
          "description": "Time-in-force.",
          "enum": ["DAY", "GTC", "IOC", "FOK"],
          "default": "DAY"
        },
        "outsideRth": {
          "type": "boolean",
          "description": "Allow execution outside regular trading hours.",
          "default": false
        },
        "clientOrderId": {
          "type": "string",
          "description": "Client-generated idempotency key.",
          "nullable": true
        },
        "transmit": {
          "type": "boolean",
          "description": "Whether to transmit the order immediately once accepted by IBKR.",
          "default": true
        }
      },
      "required": ["instrument", "side", "quantity", "orderType"],
      "additionalProperties": false
    },

    "OrderPreview": {
      "type": "object",
      "description": "Estimated impact and characteristics of an order, without sending it.",
      "properties": {
        "orderSpec": {
          "$ref": "#/$defs/OrderSpec",
          "description": "The original order specification."
        },
        "estimatedPrice": {
          "type": "number",
          "description": "Estimated execution price (e.g. mid or best available).",
          "minimum": 0,
          "nullable": true
        },
        "estimatedNotional": {
          "type": "number",
          "description": "Estimated notional value in account currency.",
          "minimum": 0,
          "nullable": true
        },
        "estimatedCommission": {
          "type": "number",
          "description": "Estimated commission and fees.",
          "minimum": 0,
          "nullable": true
        },
        "estimatedInitialMarginChange": {
          "type": "number",
          "description": "Estimated change in initial margin requirement.",
          "nullable": true
        },
        "estimatedMaintenanceMarginChange": {
          "type": "number",
          "description": "Estimated change in maintenance margin requirement.",
          "nullable": true
        },
        "warnings": {
          "type": "array",
          "description": "Human-readable warnings (e.g. low liquidity, large size).",
          "items": { "type": "string" }
        }
      },
      "required": ["orderSpec"],
      "additionalProperties": false
    },

    "OrderStatus": {
      "type": "object",
      "description": "Current status of an order at IBKR.",
      "properties": {
        "orderId": {
          "type": "string",
          "description": "Broker order identifier."
        },
        "clientOrderId": {
          "type": "string",
          "description": "Client-provided id, if any.",
          "nullable": true
        },
        "status": {
          "type": "string",
          "description": "Order lifecycle status.",
          "enum": [
            "PENDING_SUBMIT",
            "PENDING_CANCEL",
            "SUBMITTED",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELLED",
            "REJECTED",
            "EXPIRED"
          ]
        },
        "filledQuantity": {
          "type": "number",
          "description": "Total filled quantity.",
          "minimum": 0
        },
        "remainingQuantity": {
          "type": "number",
          "description": "Remaining open quantity.",
          "minimum": 0
        },
        "avgFillPrice": {
          "type": "number",
          "description": "Average fill price across fills.",
          "minimum": 0
        },
        "lastUpdate": {
          "type": "string",
          "description": "Timestamp of last status update, ISO 8601.",
          "format": "date-time"
        },
        "warnings": {
          "type": "array",
          "description": "Any broker or system warnings tied to this order.",
          "items": { "type": "string" }
        }
      },
      "required": ["orderId", "status", "filledQuantity", "remainingQuantity", "avgFillPrice", "lastUpdate"],
      "additionalProperties": false
    },

    "OrderResult": {
      "type": "object",
      "description": "Result of an attempt to place an order.",
      "properties": {
        "orderId": {
          "type": "string",
          "description": "Broker order identifier, if accepted.",
          "nullable": true
        },
        "clientOrderId": {
          "type": "string",
          "description": "Client-provided id, if any.",
          "nullable": true
        },
        "status": {
          "type": "string",
          "description": "High-level result status.",
          "enum": ["ACCEPTED", "REJECTED", "SIMULATED"],
          "nullable": false
        },
        "orderStatus": {
          "$ref": "#/$defs/OrderStatus",
          "description": "Current order status if available.",
          "nullable": true
        },
        "errors": {
          "type": "array",
          "description": "Errors returned from broker or validation.",
          "items": { "type": "string" }
        }
      },
      "required": ["status"],
      "additionalProperties": false
    },

    "CancelResult": {
      "type": "object",
      "description": "Result of a cancel order request.",
      "properties": {
        "orderId": {
          "type": "string",
          "description": "Order identifier that was requested to be cancelled."
        },
        "status": {
          "type": "string",
          "description": "Outcome of the cancel request.",
          "enum": ["CANCELLED", "ALREADY_FILLED", "NOT_FOUND", "REJECTED"]
        },
        "message": {
          "type": "string",
          "description": "Human-readable message with more detail.",
          "nullable": true
        }
      },
      "required": ["orderId", "status"],
      "additionalProperties": false
    }
  }
}
```

## CHANGELOG

**Initial version**: All core types defined.
