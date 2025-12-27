#!/usr/bin/env python3
"""
Query audit log database.

Usage:
    python scripts/query_audit_log.py --event-type ORDER_SUBMIT --limit 10
    python scripts/query_audit_log.py --account DU12345 --start 2025-01-01
    python scripts/query_audit_log.py --correlation-id abc123-def456
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ibkr_core.persistence import get_database_stats, query_audit_log


def format_audit_record(record: dict, verbose: bool = False) -> str:
    """Format audit record for display."""
    timestamp = record["timestamp"]
    event_type = record["event_type"]
    correlation_id = record.get("correlation_id", "N/A")[:16]
    account_id = record.get("account_id", "N/A")

    output = f"[{timestamp}] {event_type} (corr: {correlation_id}, acct: {account_id})"

    if verbose:
        event_data = record.get("event_data", {})
        output += f"\n  Data: {json.dumps(event_data, indent=2)}"
        if record.get("user_context"):
            output += f"\n  User: {json.dumps(record['user_context'], indent=2)}"

    return output


def main():
    parser = argparse.ArgumentParser(description="Query audit log database")
    parser.add_argument(
        "--event-type", help="Filter by event type (ORDER_PREVIEW, ORDER_SUBMIT, etc.)"
    )
    parser.add_argument("--correlation-id", help="Filter by correlation ID")
    parser.add_argument("--account", help="Filter by account ID")
    parser.add_argument("--start", help="Start time (ISO format or YYYY-MM-DD)")
    parser.add_argument("--end", help="End time (ISO format or YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=100, help="Max results (default: 100)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full event data")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--db-path", help="Database path (default: from AUDIT_DB_PATH env)")

    args = parser.parse_args()

    # Show stats if requested
    if args.stats:
        stats = get_database_stats(args.db_path)
        print("Database Statistics:")
        print(f"  Path: {stats['db_path']}")
        print(f"  Size: {stats['db_size_mb']} MB")
        print(f"  Audit log records: {stats['audit_log_count']}")
        print(f"  Order history records: {stats['order_history_count']}")
        print(f"  Schema version: {stats['schema_version']}")
        print()

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

    # Query audit log
    records = query_audit_log(
        event_type=args.event_type,
        correlation_id=args.correlation_id,
        account_id=args.account,
        start_time=start_time,
        end_time=end_time,
        limit=args.limit,
        offset=args.offset,
        db_path=args.db_path,
    )

    if not records:
        print("No audit records found matching criteria.")
        return 0

    print(f"Found {len(records)} audit record(s):\n")

    for record in records:
        print(format_audit_record(record, verbose=args.verbose))
        print()

    # Show pagination info
    if len(records) == args.limit:
        print(f"Showing records {args.offset + 1}-{args.offset + len(records)}")
        print(f"Use --offset {args.offset + args.limit} to see more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
