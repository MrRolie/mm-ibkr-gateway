"""
Phase 1 Integration Test Script.

Tests IBKRClient and contract resolution against the paper gateway.
Run with: python scripts/test_phase1.py
"""

import sys
import random

# Add parent to path
sys.path.insert(0, ".")

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

print("=" * 60)
print("PHASE 1 INTEGRATION TEST - IBKR Paper Gateway")
print("=" * 60)

from ibkr_core.client import IBKRClient
from ibkr_core.contracts import (
    resolve_contract,
    resolve_contracts,
    get_front_month_expiry,
    get_contract_cache,
)
from ibkr_core.models import SymbolSpec

client_id = random.randint(5000, 9999)
print(f"\nUsing client ID: {client_id}")

# Create client
client = IBKRClient(mode="paper", client_id=client_id)

try:
    # Test 1: Connect
    print("\n[TEST 1] Connecting to paper gateway...")
    client.connect(timeout=15)
    print(f"  OK - Connected: {client.is_connected}")
    print(f"  OK - Accounts: {client.managed_accounts}")

    # Test 2: Resolve AAPL stock
    print("\n[TEST 2] Resolving AAPL (STK)...")
    spec = SymbolSpec(symbol="AAPL", securityType="STK")
    contract = resolve_contract(spec, client)
    print(f"  OK - conId: {contract.conId}")
    print(f"  OK - exchange: {contract.exchange}")
    print(f"  OK - currency: {contract.currency}")

    # Test 3: Resolve SPY ETF
    print("\n[TEST 3] Resolving SPY (ETF)...")
    spec = SymbolSpec(symbol="SPY", securityType="ETF")
    contract = resolve_contract(spec, client)
    print(f"  OK - conId: {contract.conId}")
    print(f"  OK - exchange: {contract.exchange}")

    # Test 4: Resolve MES futures (front month)
    print("\n[TEST 4] Resolving MES (FUT - front month)...")
    spec = SymbolSpec(symbol="MES", securityType="FUT")
    contract = resolve_contract(spec, client)
    print(f"  OK - conId: {contract.conId}")
    print(f"  OK - expiry: {contract.lastTradeDateOrContractMonth}")
    print(f"  OK - exchange: {contract.exchange}")

    # Test 5: Resolve ES e-mini futures
    print("\n[TEST 5] Resolving ES (FUT - front month)...")
    spec = SymbolSpec(symbol="ES", securityType="FUT")
    contract = resolve_contract(spec, client)
    print(f"  OK - conId: {contract.conId}")
    print(f"  OK - expiry: {contract.lastTradeDateOrContractMonth}")

    # Test 6: Resolve SPX index
    print("\n[TEST 6] Resolving SPX (IND)...")
    spec = SymbolSpec(symbol="SPX", securityType="IND")
    contract = resolve_contract(spec, client)
    print(f"  OK - conId: {contract.conId}")
    print(f"  OK - exchange: {contract.exchange}")

    # Test 7: Batch resolution
    print("\n[TEST 7] Batch resolving MSFT, GOOGL, AMZN...")
    specs = [
        SymbolSpec(symbol="MSFT", securityType="STK"),
        SymbolSpec(symbol="GOOGL", securityType="STK"),
        SymbolSpec(symbol="AMZN", securityType="STK"),
    ]
    contracts = resolve_contracts(specs, client)
    for sym, c in contracts.items():
        print(f"  OK - {sym}: conId={c.conId}")

    # Test 8: Cache verification
    print("\n[TEST 8] Verifying cache works...")
    cache = get_contract_cache()
    stats_before = cache.stats.copy()
    # Re-resolve AAPL - should hit cache
    spec = SymbolSpec(symbol="AAPL", securityType="STK")
    contract = resolve_contract(spec, client)
    stats_after = cache.stats
    print(f"  OK - Cache hits: {stats_after['hits']} (was {stats_before['hits']})")
    print(f"  OK - Cache size: {cache.size}")

    # Test 9: Front month expiry helper
    print("\n[TEST 9] Getting front month expiry for MNQ...")
    expiry = get_front_month_expiry("MNQ", client)
    print(f"  OK - MNQ front month: {expiry}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED - IBKR contracts resolved successfully!")
    print("=" * 60)

except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
finally:
    client.disconnect()
    print("\nDisconnected from IBKR Gateway")
