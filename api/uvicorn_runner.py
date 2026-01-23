"""Runner wrapper that ensures stdout/stderr objects exist and launches Uvicorn.

This avoids issues when the process is started with redirected stdio where
`sys.stdout` can be None and third-party loggers call `sys.stdout.isatty()`.
"""
import sys

# Ensure sys.stdout / sys.stderr provide isatty
class _DummyStream:
    def write(self, _):
        return
    def flush(self):
        return
    def isatty(self):
        return False

if getattr(sys, "stdout", None) is None:
    sys.stdout = _DummyStream()
if getattr(sys, "stderr", None) is None:
    sys.stderr = _DummyStream()

# Arg parsing and run
from typing import Optional
import argparse
from uvicorn import run
from ibkr_core.config import get_config

config = get_config()

parser = argparse.ArgumentParser(description="Run uvicorn with safe stdout/stderr handling")
parser.add_argument("--host", default=config.api_bind_host)
parser.add_argument("--port", type=int, default=config.api_port)
parser.add_argument("--log-level", default=config.log_level.lower())
args = parser.parse_args()

# Run the application using api.boot:app to ensure early event loop setup
run("api.boot:app", host=args.host, port=args.port, log_level=args.log_level)
