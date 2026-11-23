"""Production server entry point: python -m univio --host 0.0.0.0."""

import argparse

import uvicorn

from univio.runtime import run_async


def main():
    parser = argparse.ArgumentParser(description="Run the Univio API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    config = uvicorn.Config(
        "univio.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        access_log=False,
        proxy_headers=False,
        limit_concurrency=100,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=30,
    )
    run_async(uvicorn.Server(config).serve())


if __name__ == "__main__":
    main()
