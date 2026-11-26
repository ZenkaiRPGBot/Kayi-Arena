"""Lightweight aiohttp HTTP server for Render Web Service health & optional webhook."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from aiohttp import web

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher


def build_health_app(
    *,
    service_name: str = "kayi-arena",
    extra_status: dict[str, Any] | None = None,
    readiness_check: Callable[[], tuple[bool, str]] | None = None,
    bot: Bot | None = None,
    dp: Dispatcher | None = None,
    webhook_path: str | None = None,
    webhook_secret: str = "",
) -> web.Application:
    """Create an aiohttp app exposing `/`, `/health`, and optional Telegram webhook."""
    app = web.Application()

    async def handle_root(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "service": service_name,
                "status": "ok",
            }
        )

    async def handle_health(_request: web.Request) -> web.Response:
        status = "ok"
        http_code = 200
        payload: dict[str, Any] = {
            "status": status,
            "service": service_name,
        }
        if readiness_check is not None:
            ok, msg = readiness_check()
            payload["database"] = msg
            if not ok:
                payload["status"] = "degraded"
                http_code = 503
        if extra_status:
            payload.update(extra_status)
        return web.json_response(payload, status=http_code)

    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)

    if bot is not None and dp is not None and webhook_path:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

        path = webhook_path if webhook_path.startswith("/") else f"/{webhook_path}"
        handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=webhook_secret or None,
        )
        handler.register(app, path=path)
        setup_application(app, dp, bot=bot)

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
