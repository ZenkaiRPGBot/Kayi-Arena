"""Lightweight aiohttp HTTP server for Render Web Service health checks."""

from __future__ import annotations

from typing import Any

from aiohttp import web


def build_health_app(
    *,
    service_name: str = "kayi-arena",
    extra_status: dict[str, Any] | None = None,
) -> web.Application:
    """Create a lightweight aiohttp app exposing `/` and `/health`."""
    app = web.Application()

    async def handle_root(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "service": service_name,
                "status": "ok",
            }
        )

    async def handle_health(_request: web.Request) -> web.Response:
        payload: dict[str, Any] = {
            "status": "ok",
            "service": service_name,
        }
        if extra_status:
            payload.update(extra_status)
        return web.json_response(payload)

    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    return app


async def start_http_server(
    app: web.Application,
    *,
    host: str = "0.0.0.0",
    port: int = 10000,
) -> tuple[web.AppRunner, web.TCPSite]:
    """Start the aiohttp AppRunner + TCPSite and return both for graceful cleanup."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    return runner, site
