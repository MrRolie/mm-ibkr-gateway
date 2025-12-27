"""
Legacy entry point for healthcheck. Use scripts/healthcheck.py instead.

Usage:
    python -m ibkr_core (legacy, redirects to scripts.healthcheck)
    python scripts/healthcheck.py (preferred)

Connects to IBKR, queries server time, prints it, then disconnects.
Exit codes:
    0 = success
    1 = error (IBKR down, connection failure, etc.)
"""

import sys
import warnings

from scripts.healthcheck import main

warnings.warn(
    "Using 'python -m ibkr_core' is deprecated. Use 'python scripts/healthcheck.py' instead.",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    sys.exit(main())
