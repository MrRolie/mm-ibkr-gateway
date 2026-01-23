#!/usr/bin/env python3
"""
Test audit logging with a real order flow.

This script:
1. Connects to paper gateway
2. Previews and places a test order
3. Queries the audit database to verify logging
4. Cancels the order
5. Verifies cancellation is logged
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ibkr_core.client import IBKRClient
from ibkr_core.config import get_config
from ibkr_core.logging_config import configure_logging, set_correlation_id
from ibkr_core.models import OrderSpec, SymbolSpec
from ibkr_core.orders import cancel_order, place_order, preview_order
from ibkr_core.persistence import get_database_stats, query_audit_log, query_orders


def main():
    # Configure logging
    configure_logging(format_type="text", force_reconfigure=True)

    print("=" * 60)
    print("AUDIT LOGGING TEST")
    print("=" * 60)

    # Get config
    config = get_config()
    print(f"\nConfiguration:")
    print(f"  Trading mode: {config.trading_mode}")
    print(f"  Orders enabled: {config.orders_enabled}")

    # Set a test correlation ID
    test_correlation_id = "test-audit-12345"
    set_correlation_id(test_correlation_id)
    print(f"  Correlation ID: {test_correlation_id}")

    # Connect to paper gateway
    print("\n1. Connecting to IBKR Paper Gateway...")
    client = IBKRClient(mode="paper")
    client.connect()

    account_id = client.managed_accounts[0] if client.managed_accounts else None
    print(f"   Connected! Account: {account_id}")

    try:
        # Create a test order spec - far from market limit order
        print("\n2. Creating test order spec...")
        symbol_spec = SymbolSpec(
            symbol="AAPL",
            securityType="STK",
            exchange="SMART",
            currency="USD",
        )

        order_spec = OrderSpec(
            instrument=symbol_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=100.00,  # Far below market - won't fill
            accountId=account_id,
        )
        print(f"   Order: BUY 1 AAPL @ $100 LMT (far from market)")

        # Preview the order
        print("\n3. Previewing order...")
        preview = None
        try:
            preview = preview_order(client, order_spec, timeout_s=15.0)
            print(f"   Estimated price: ${preview.estimatedPrice:.2f}")
            print(f"   Estimated notional: ${preview.estimatedNotional:.2f}")
            if preview.warnings:
                print(f"   Warnings: {preview.warnings}")
        except Exception as e:
            print(f"   Preview failed: {e}")
            print("   (Continuing with place order anyway...)")

        # Place the order (if orders enabled)
        if config.orders_enabled:
            print("\n4. Placing order...")
            try:
                result = place_order(client, order_spec, wait_for_status_s=5.0)
                print(f"   Order ID: {result.orderId}")
                print(f"   Status: {result.status}")
                if result.orderStatus:
                    print(f"   IBKR Status: {result.orderStatus.status}")

                # Cancel the order
                if result.orderId and result.status == "ACCEPTED":
                    print("\n5. Cancelling order...")
                    cancel_result = cancel_order(client, result.orderId)
                    print(f"   Cancel status: {cancel_result.status}")
                    print(f"   Message: {cancel_result.message}")
            except Exception as e:
                print(f"   Order placement failed: {e}")
        else:
            print("\n4. orders_enabled=false - skipping actual order placement")
            print("   Set orders_enabled=true in control.json to test real order flow")

    finally:
        # Disconnect
        print("\n6. Disconnecting...")
        client.disconnect()
        print("   Disconnected!")

    # Query the audit database
    print("\n" + "=" * 60)
    print("AUDIT DATABASE VERIFICATION")
    print("=" * 60)

    # Get database stats
    stats = get_database_stats()
    print(f"\nDatabase Stats:")
    print(f"  Path: {stats['db_path']}")
    print(f"  Audit log records: {stats['audit_log_count']}")
    print(f"  Order history records: {stats['order_history_count']}")

    # Query events for this test
    print(f"\nAudit events for correlation ID '{test_correlation_id}':")
    events = query_audit_log(correlation_id=test_correlation_id)
    if events:
        for event in events:
            print(f"  [{event['timestamp']}] {event['event_type']}")
            print(f"    Account: {event.get('account_id', 'N/A')}")
            print(f"    Data: {event['event_data']}")
    else:
        print("  No events found for this correlation ID")

    # Query recent audit events
    print(f"\nRecent audit events (last 10):")
    recent_events = query_audit_log(limit=10)
    for event in recent_events:
        corr = event.get("correlation_id", "N/A")[:16] if event.get("correlation_id") else "N/A"
        print(
            f"  [{event['timestamp']}] {event['event_type']} (acct: {event.get('account_id', 'N/A')}, corr: {corr})"
        )

    # Query order history
    print(f"\nOrder history for account {account_id}:")
    orders = query_orders(account_id=account_id, limit=5)
    if orders:
        for order in orders:
            print(
                f"  [{order['placed_at']}] {order['side']} {order['quantity']} {order['symbol']} @ {order['order_type']}"
            )
            print(f"    Status: {order['status']}, Order ID: {order['order_id']}")
    else:
        print("  No orders found")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
