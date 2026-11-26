"""Telegram handlers package for Kayi Arena."""

from app.telegram.handlers.admin import build_admin_router
from app.telegram.handlers.callbacks import build_callbacks_router
from app.telegram.handlers.commands import build_commands_router
from app.telegram.handlers.errors import build_errors_router

__all__ = [
    "build_admin_router",
    "build_callbacks_router",
    "build_commands_router",
    "build_errors_router",
]
