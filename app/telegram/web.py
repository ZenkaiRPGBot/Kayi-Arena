"""Lightweight aiohttp HTTP server for Render Web Service health, pinger & webhook."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from aiohttp import ClientSession, ClientTimeout, web

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher

logger = logging.getLogger(__name__)


def _format_uptime(seconds: int) -> str:
    hours, rem = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


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
    """Create an aiohttp app exposing `/`, `/ping`, `/health`, and optional Telegram webhook."""
    app = web.Application()
    started_at = time.monotonic()

    async def handle_root(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "service": service_name,
                "status": "ok",
            }
        )

    async def handle_ping(_request: web.Request) -> web.Response:
        uptime_str = _format_uptime(int(time.monotonic() - started_at))
        return web.json_response(
            {
                "status": "ok",
                "service": service_name,
                "uptime": uptime_str,
            }
        )

    async def handle_health(_request: web.Request) -> web.Response:
        status = "ok"
        http_code = 200
        payload: dict[str, Any] = {
            "status": status,
            "service": service_name,
            "uptime": _format_uptime(int(time.monotonic() - started_at)),
        }
        if readiness_check is not None:
            try:
                ok, msg = await asyncio.to_thread(readiness_check)
            except Exception as exc:
                ok, msg = False, f"readiness error: {type(exc).__name__}"
            payload["database"] = msg
            if not ok:
                payload["status"] = "degraded"
                http_code = 503
        if extra_status:
            payload.update(extra_status)
        return web.json_response(payload, status=http_code)

    app.router.add_get("/", handle_root)
    app.router.add_get("/ping", handle_ping)
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


async def _wait_or_stop(stop_event: asyncio.Event, delay: float) -> bool:
    """Sleep up to ``delay`` seconds, returning True if ``stop_event`` was set."""
    if delay <= 0:
        return stop_event.is_set()
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=delay)
        return True
    except asyncio.TimeoutError:
        return False


async def run_self_ping_loop(
    *,
    ping_url: str,
    stop_event: asyncio.Event,
    initial_delay: float = 60.0,
    interval: float = 600.0,
    timeout_seconds: float = 10.0,
    session_factory: Callable[..., ClientSession] | None = None,
) -> None:
    """Lightweight, fault-tolerant keep-alive pinger reusing a single HTTP session."""
    if not ping_url:
        return
    if await _wait_or_stop(stop_event, initial_delay):
        return

    timeout = ClientTimeout(total=max(1.0, timeout_seconds))
    make_session = session_factory or (lambda: ClientSession(timeout=timeout))
    async with make_session() as session:
        while not stop_event.is_set():
            try:
                async with session.get(ping_url) as response:
                    logger.debug("Self-ping %s -> HTTP %d", ping_url, response.status)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Self-ping failed: %s", type(exc).__name__)
            if await _wait_or_stop(stop_event, interval):
                break
