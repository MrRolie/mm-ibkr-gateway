#!/usr/bin/env python3
"""
Export order history to CSV.

Usage:
    python scripts/export_order_history.py --output orders.csv
    python scripts/export_order_history.py --account DU12345 --symbol AAPL --output aapl_orders.csv
    python scripts/export_order_history.py --start 2025-01-01 --end 2025-01-31 --output jan_orders.csv
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ibkr_core.persistence import query_orders


def export_to_csv(records: list, output_path: str) -> None:
    """Export order records to CSV."""
    if not records:
        print("No records to export.")
        return

    # Define CSV columns
    fieldnames = [
        "order_id",
        "correlation_id",
        "account_id",
        "symbol",
        "side",
        "quantity",
        "order_type",
        "status",
        "placed_at",
        "updated_at",
        "ibkr_order_id",
        "estimated_price",
        "estimated_notional",
        "fill_price",
        "fill_quantity",
        "trading_mode",
        "orders_enabled",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            # Extract nested data
            preview_data = record.get("preview_data") or {}
            fill_data = record.get("fill_data") or {}
            config_snapshot = record.get("config_snapshot") or {}

            row = {
                "order_id": record["order_id"],
                "correlation_id": record.get("correlation_id", ""),
                "account_id": record["account_id"],
                "symbol": record["symbol"],
                "side": record["side"],
                "quantity": record["quantity"],
                "order_type": record["order_type"],
                "status": record["status"],
                "placed_at": record["placed_at"],
                "updated_at": record["updated_at"],
                "ibkr_order_id": record.get("ibkr_order_id", ""),
                "estimated_price": preview_data.get("estimatedPrice", ""),
                "estimated_notional": preview_data.get("estimatedNotional", ""),
                "fill_price": fill_data.get("fill_price", ""),
                "fill_quantity": fill_data.get("fill_quantity", ""),
                "trading_mode": config_snapshot.get("trading_mode", ""),
                "orders_enabled": config_snapshot.get("orders_enabled", ""),
            }

            writer.writerow(row)

    print(f"Exported {len(records)} orders to {output_path}")


def export_to_json(records: list, output_path: str, pretty: bool = True) -> None:
    """Export order records to JSON."""
    if not records:
        print("No records to export.")
        return

    with open(output_path, "w") as f:
        if pretty:
            json.dump(records, f, indent=2, default=str)
        else:
            json.dump(records, f, default=str)

    print(f"Exported {len(records)} orders to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Export order history")
    parser.add_argument("--output", "-o", required=True, help="Output file path")
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument("--account", help="Filter by account ID")
    parser.add_argument("--symbol", help="Filter by symbol")
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument("--correlation-id", help="Filter by correlation ID")
    parser.add_argument("--start", help="Start time (ISO format or YYYY-MM-DD)")
    parser.add_argument("--end", help="End time (ISO format or YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=1000, help="Max results (default: 1000)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--db-path", help="Database path (default: from AUDIT_DB_PATH env)")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON (for JSON format)")

    args = parser.parse_args()

    # Parse dates
    start_time = None
    end_time = None

    if args.start:
        try:
            start_time = args.start if "T" in args.start else f"{args.start}T00:00:00"
        except ValueError:
            print(f"Invalid start time: {args.start}", file=sys.stderr)
            return 1

    if args.end:
        try:
            end_time = args.end if "T" in args.end else f"{args.end}T23:59:59"
        except ValueError:
            print(f"Invalid end time: {args.end}", file=sys.stderr)
            return 1

    # Query orders
    print("Querying order history...")
    records = query_orders(
        account_id=args.account,
        symbol=args.symbol,
        status=args.status,
        correlation_id=args.correlation_id,
        start_time=start_time,
        end_time=end_time,
        limit=args.limit,
        offset=args.offset,
        db_path=args.db_path,
    )

    if not records:
        print("No orders found matching criteria.")
        return 0

    print(f"Found {len(records)} order(s)")

    # Export
    if args.format == "csv":
        export_to_csv(records, args.output)
    else:
        export_to_json(records, args.output, pretty=args.pretty)

    return 0


if __name__ == "__main__":
    sys.exit(main())
