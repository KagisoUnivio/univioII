"""Run async entry points with a PostgreSQL-compatible event loop on Windows."""

import asyncio
import sys


def run_async(coroutine):
    """Python 3.11 Runner avoids changing global event-loop policy at import."""
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coroutine)
