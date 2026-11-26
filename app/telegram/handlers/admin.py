"""Owner-only /admin dashboard and operations handlers for Kayi Arena (Module 9)."""

from __future__ import annotations

import asyncio
import html
import logging
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from app.database import EvaluationStatus, HELD_NARUTO_NAMES
from app.engine import TerminationReason
from app.telegram.constants import STYLE_DANGER, STYLE_PRIMARY, STYLE_SUCCESS
from app.telegram.safe_api import (
    answer_callback_safe,
    edit_message_text_safe,
    send_message_safe,
)
from app.telegram.service import ArenaTelegramCoordinator
from app.telegram.texts import clamp_text, esc

logger = logging.getLogger(__name__)


def _btn(
    text: str,
    cb: str,
    *,
    style: str | None = None,
) -> InlineKeyboardButton:
    kwargs: dict[str, Any] = {"text": text, "callback_data": cb}
    if style is not None:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def _is_authorized_private(
    user: User | None, chat: Chat | None, coordinator: ArenaTelegramCoordinator
) -> tuple[bool, str]:
    if user is None or not coordinator.config.is_admin(user.id):
        return False, "⛔ Unauthorized. This action is restricted to bot administrators."
    if chat is None or chat.type != "private":
        return False, "🔒 Admin operations are restricted to private chats."
    return True, ""


def _format_uptime(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {mins}m"
    if hours > 0:
        return f"{hours}h {mins}m {secs}s"
    return f"{mins}m {secs}s"


def _render_dashboard(coordinator: ArenaTelegramCoordinator) -> tuple[str, InlineKeyboardMarkup]:
    uptime = _format_uptime(coordinator.uptime_seconds())
    db_ok, db_msg = coordinator.store.integrity_check() if coordinator.store else (True, "in-memory")
    stats = coordinator.store.get_stats_snapshot() if coordinator.store else {}
    total_users = stats.get("total_users", len(coordinator._player_names))
    active_matches = stats.get("active_matches", len(coordinator.manager._matches))
    pending_challenges = stats.get("open_challenges", 0)
    avail_universes = len(coordinator.eligible_universes())
    maint = "ON 🔧" if coordinator.is_maintenance_mode() else "OFF"

    text = clamp_text(
        "\n".join(
            [
                "⚙️ <b>KAYI ARENA ADMIN</b>",
                "",
                "Bot status: <b>Online</b>",
                f"Uptime: <code>{uptime}</code>",
                f"Database: <b>{'OK' if db_ok else 'ERROR'}</b> ({esc(db_msg)})",
                f"Maintenance mode: <b>{maint}</b>",
                f"Total users: <b>{total_users}</b>",
                f"Active matches: <b>{active_matches}</b>",
                f"Pending challenges: <b>{pending_challenges}</b>",
                f"Available universes: <b>{avail_universes}</b>",
            ]
        )
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("📊 Bot Statistics", "adm:stats"),
                _btn("🩺 Diagnostics", "adm:diag"),
            ],
            [_btn("🌐 Manage Universes", "adm:univ")],
            [_btn("📚 Manage Characters", "adm:chars:menu")],
            [_btn("📦 Manage Datasets", "adm:dsets")],
            [_btn("🎮 Active Matches", "adm:matches")],
            [_btn("📢 Broadcast", "adm:bcast")],
            [_btn("💾 Database Backup", "adm:backup")],
            [_btn("🔧 Maintenance Mode", "adm:maint")],
            [
                _btn("🔄 Refresh", "adm:dash", style=STYLE_PRIMARY),
                _btn("✖ Close", "adm:close", style=STYLE_DANGER),
            ],
        ]
    )
    return text, kb


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("« Back to Admin", "adm:dash")]]
    )


async def cmd_admin(message: Message, coordinator: ArenaTelegramCoordinator) -> None:
    ok, err = _is_authorized_private(message.from_user, message.chat, coordinator)
    if not ok:
        await send_message_safe(coordinator.bot, chat_id=message.chat.id, text=err)
        return
    text, kb = _render_dashboard(coordinator)
    await send_message_safe(
        coordinator.bot, chat_id=message.chat.id, text=text, reply_markup=kb
    )


async def handle_broadcast_input(
    message: Message, coordinator: ArenaTelegramCoordinator
) -> None:
    if message.from_user is None or not coordinator.config.is_admin(message.from_user.id):
        return
    if message.chat.type != "private":
        return
    uid = str(message.from_user.id)
    if not coordinator.is_awaiting_broadcast(uid):
        return
    raw_text = (message.text or "").strip()
    if not raw_text or raw_text.startswith("/"):
        return
    coordinator.set_broadcast_draft(uid, raw_text)
    targets = coordinator.store.list_known_chats() if coordinator.store else []
    preview = clamp_text(
        "\n".join(
            [
                "📢 <b>Broadcast Preview</b>",
                "",
                esc(raw_text),
                "",
                f"Target chats: <b>{len(targets)}</b>",
                "Confirm sending this broadcast?",
            ]
        )
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("✅ Yes, Send Broadcast", "adm:bsend", style=STYLE_SUCCESS),
                _btn("✖ Cancel", "adm:bcanc", style=STYLE_DANGER),
            ]
        ]
    )
    await send_message_safe(
        coordinator.bot, chat_id=message.chat.id, text=preview, reply_markup=kb
    )


async def handle_admin_callback(
    query: CallbackQuery, coordinator: ArenaTelegramCoordinator
) -> None:
    msg = query.message
    ok, err = _is_authorized_private(
        query.from_user, msg.chat if msg else None, coordinator
    )
    if not ok:
        await answer_callback_safe(query, err, show_alert=True)
        return
    assert msg is not None and query.from_user is not None

    actor_id = str(query.from_user.id)
    chat_id = str(msg.chat.id)
    msg_id = msg.message_id
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else "dash"
    args = parts[2:]

    if action == "close":
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text="⚙️ Admin panel closed.",
            reply_markup=None,
        )
        await answer_callback_safe(query)
        return

    if action == "dash":
        text, kb = _render_dashboard(coordinator)
        await edit_message_text_safe(
            coordinator.bot, chat_id=chat_id, message_id=msg_id, text=text, reply_markup=kb
        )
        await answer_callback_safe(query)
        return

    if action == "stats":
        stats = coordinator.store.get_stats_snapshot() if coordinator.store else {}
        text = clamp_text(
            "\n".join(
                [
                    "📊 <b>Bot Statistics</b>",
                    "",
                    f"Registered players: <b>{stats.get('total_users', len(coordinator._player_names))}</b>",
                    f"Known private chats: <b>{stats.get('private_chats', 0)}</b>",
                    f"Known group chats: <b>{stats.get('group_chats', 0)}</b>",
                    f"Active matches: <b>{stats.get('active_matches', len(coordinator.manager._matches))}</b>",
                    f"Completed matches: <b>{stats.get('completed_matches', 0)}</b>",
                    f"Total historical matches: <b>{stats.get('total_history', 0)}</b>",
                    f"Open challenges: <b>{stats.get('open_challenges', 0)}</b>",
                ]
            )
        )
        await edit_message_text_safe(
            coordinator.bot, chat_id=chat_id, message_id=msg_id, text=text, reply_markup=_back_kb()
        )
        await answer_callback_safe(query)
        return

    if action == "diag":
        db_ok, db_msg = coordinator.store.integrity_check() if coordinator.store else (True, "in-memory")
        text = clamp_text(
            "\n".join(
                [
                    "🩺 <b>System Diagnostics</b>",
                    "",
                    f"Uptime: <code>{_format_uptime(coordinator.uptime_seconds())}</code>",
                    f"Python: <code>{platform.python_version()}</code> ({esc(platform.system())})",
                    f"Transport mode: <code>{esc(coordinator.config.transport_mode)}</code>",
                    f"Dataset kind: <code>{esc(coordinator.config.dataset_kind.value)}</code>",
                    f"SQLite integrity: <b>{'OK' if db_ok else 'FAILED'}</b> ({esc(db_msg)})",
                    f"Maintenance mode: <b>{'ON' if coordinator.is_maintenance_mode() else 'OFF'}</b>",
                ]
            )
        )
        await edit_message_text_safe(
            coordinator.bot, chat_id=chat_id, message_id=msg_id, text=text, reply_markup=_back_kb()
        )
        await answer_callback_safe(query)
        return

    # ------------------------------------------------------------------
    # Universe Management
    # ------------------------------------------------------------------
    if action == "univ":
        universes = coordinator.db.list_universes(active_only=False)
        lines = ["🌐 <b>Manage Universes</b>", ""]
        rows: list[list[InlineKeyboardButton]] = []
        for u in universes:
            state_lbl = "✅ Active" if u.active else "⏸ Inactive"
            lines.append(f"• <b>{esc(u.name)}</b> (<code>{esc(u.universe_id)}</code>) — {state_lbl}")
            btn_lbl = f"Deactivate {u.name}" if u.active else f"Activate {u.name}"
            rows.append([_btn(btn_lbl, f"adm:utog:{u.universe_id}")])
        if not universes:
            lines.append("No universes registered.")
        rows.append([_btn("« Back to Admin", "adm:dash")])
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=clamp_text("\n".join(lines)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await answer_callback_safe(query)
        return

    if action == "utog" and args:
        uid = args[0]
        u = coordinator.db.get_universe(uid)
        verb = "Deactivate" if u.active else "Activate"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn(f"Confirm {verb}", f"adm:uconf:{uid}", style=STYLE_DANGER if u.active else STYLE_SUCCESS),
                    _btn("Cancel", "adm:univ"),
                ]
            ]
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"⚠️ {verb} universe <b>{esc(u.name)}</b>?",
            reply_markup=kb,
        )
        await answer_callback_safe(query)
        return

    if action == "uconf" and args:
        uid = args[0]
        u = coordinator.db.get_universe(uid)
        updated = coordinator.db.set_universe_active(uid, not u.active)
        if coordinator.store:
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="toggle_universe_active",
                target_type="universe",
                target_id=uid,
                details={"active": updated.active},
            )
        await answer_callback_safe(
            query, f"{updated.name} is now {'active' if updated.active else 'inactive'}."
        )
        # Refresh universe list
        query_copy = query
        parts[:] = ["adm", "univ"]
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"✅ Universe <b>{esc(updated.name)}</b> updated ({'Active' if updated.active else 'Inactive'}).",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("« Manage Universes", "adm:univ")]]
            ),
        )
        return

    # ------------------------------------------------------------------
    # Character Evaluation Review & Approval
    # ------------------------------------------------------------------
    if action == "chars":
        sub = args[0] if args else "menu"
        universes = coordinator.db.list_universes(active_only=False)
        if sub == "menu":
            rows = [
                [_btn(f"{u.name}", f"adm:chars:{u.universe_id}:review:0")]
                for u in universes
            ]
            rows.append([_btn("« Back to Admin", "adm:dash")])
            await edit_message_text_safe(
                coordinator.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text="📚 <b>Manage Characters</b>\n\nSelect a universe to inspect Draft, Review, and Approved records.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
            await answer_callback_safe(query)
            return

        uid = sub
        status_str = args[1] if len(args) > 1 else "review"
        page = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
        ev_status = EvaluationStatus(status_str)
        chars = coordinator.db.list_characters(universe_id=uid, status=ev_status)
        per_page = 6
        total_pages = max(1, (len(chars) + per_page - 1) // per_page)
        safe_page = max(0, min(page, total_pages - 1))
        chunk = chars[safe_page * per_page : (safe_page + 1) * per_page]

        lines = [
            f"📚 <b>{esc(uid)} — {esc(ev_status.value.title())}</b> ({len(chars)})",
            "",
        ]
        rows = []
        for ch in chunk:
            lines.append(
                f"• <b>{esc(ch.name)}</b> ({esc(ch.rarity)}) — Img: <code>{esc(ch.image.status.value)}</code>"
            )
            if ev_status is EvaluationStatus.REVIEW:
                rows.append([_btn(f"Approve {ch.name[:18]}", f"adm:chappr:{ch.character_id}", style=STYLE_SUCCESS)])
            elif ev_status is EvaluationStatus.APPROVED:
                rows.append([_btn(f"Reopen {ch.name[:18]}", f"adm:chreopen:{ch.character_id}")])

        rows.append(
            [
                _btn("Draft", f"adm:chars:{uid}:draft:0"),
                _btn("Review", f"adm:chars:{uid}:review:0"),
                _btn("Approved", f"adm:chars:{uid}:approved:0"),
            ]
        )
        rows.append(
            [
                _btn("📤 Submit Non-Held Drafts", f"adm:chsuball:{uid}"),
                _btn("✅ Batch Approve Review", f"adm:chappall:{uid}", style=STYLE_SUCCESS),
            ]
        )
        nav: list[InlineKeyboardButton] = []
        if safe_page > 0:
            nav.append(_btn("‹", f"adm:chars:{uid}:{status_str}:{safe_page - 1}"))
        nav.append(_btn(f"{safe_page + 1}/{total_pages}", "adm:dash"))
        if safe_page + 1 < total_pages:
            nav.append(_btn("›", f"adm:chars:{uid}:{status_str}:{safe_page + 1}"))
        rows.append(nav)
        rows.append([_btn("« Back to Admin", "adm:dash")])

        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=clamp_text("\n".join(lines)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await answer_callback_safe(query)
        return

    if action == "chappr" and args:
        cid = args[0]
        entry = coordinator.db.get_character_entry(cid)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn("Confirm Approval", f"adm:chconf:{cid}", style=STYLE_SUCCESS),
                    _btn("Cancel", f"adm:chars:{entry.universe_id}:review:0"),
                ]
            ]
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"⚠️ Approve <b>{esc(entry.name)}</b> (<code>{esc(cid)}</code>) for publication?",
            reply_markup=kb,
        )
        await answer_callback_safe(query)
        return

    if action == "chconf" and args:
        cid = args[0]
        entry = coordinator.db.approve_character(cid)
        if coordinator.store:
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="approve_character",
                target_type="character",
                target_id=cid,
                details={"universe_id": entry.universe_id},
            )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"✅ Approved <b>{esc(entry.name)}</b>.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("« Back to Characters", f"adm:chars:{entry.universe_id}:review:0")]]
            ),
        )
        await answer_callback_safe(query, "Character approved.")
        return

    if action == "chreopen" and args:
        cid = args[0]
        entry = coordinator.db.reopen_to_draft(cid)
        if coordinator.store:
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="reopen_character_draft",
                target_type="character",
                target_id=cid,
                details={"universe_id": entry.universe_id},
            )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"↩️ Reopened <b>{esc(entry.name)}</b> to Draft.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("« Back to Characters", f"adm:chars:{entry.universe_id}:approved:0")]]
            ),
        )
        await answer_callback_safe(query, "Reopened to Draft.")
        return

    if action == "chsuball" and args:
        uid = args[0]
        drafts = coordinator.db.list_characters(universe_id=uid, status=EvaluationStatus.DRAFT)
        submitted = 0
        held_skipped = 0
        for ch in drafts:
            if ch.name in HELD_NARUTO_NAMES:
                held_skipped += 1
                continue
            coordinator.db.submit_for_review(ch.character_id)
            submitted += 1
        if coordinator.store:
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="batch_submit_review",
                target_type="universe",
                target_id=uid,
                details={"submitted": submitted, "held_skipped": held_skipped},
            )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"📤 Submitted <b>{submitted}</b> non-held Draft characters to Review.\n⏸ Held preserved: <b>{held_skipped}</b>.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("« View Review Queue", f"adm:chars:{uid}:review:0")]]
            ),
        )
        await answer_callback_safe(query, f"Submitted {submitted} to Review.")
        return

    if action == "chappall" and args:
        uid = args[0]
        in_review = [
            c
            for c in coordinator.db.list_characters(universe_id=uid, status=EvaluationStatus.REVIEW)
            if c.name not in HELD_NARUTO_NAMES
        ]
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn(f"Confirm Approve ({len(in_review)})", f"adm:chappallc:{uid}", style=STYLE_SUCCESS),
                    _btn("Cancel", f"adm:chars:{uid}:review:0"),
                ]
            ]
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"⚠️ Approve <b>{len(in_review)}</b> non-held Review characters in <code>{esc(uid)}</code> for publication?\n\nHeld characters remain excluded.",
            reply_markup=kb,
        )
        await answer_callback_safe(query)
        return

    if action == "chappallc" and args:
        uid = args[0]
        in_review = coordinator.db.list_characters(universe_id=uid, status=EvaluationStatus.REVIEW)
        approved = 0
        for ch in in_review:
            if ch.name in HELD_NARUTO_NAMES:
                continue
            coordinator.db.approve_character(ch.character_id)
            approved += 1
        if coordinator.store:
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="batch_approve_characters",
                target_type="universe",
                target_id=uid,
                details={"approved": approved},
            )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"✅ Batch-approved <b>{approved}</b> non-held characters in <code>{esc(uid)}</code>.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [_btn("📦 Go to Datasets", "adm:dsets", style=STYLE_PRIMARY)],
                    [_btn("« Back to Characters", f"adm:chars:{uid}:approved:0")],
                ]
            ),
        )
        await answer_callback_safe(query, f"Approved {approved} characters.")
        return

    # ------------------------------------------------------------------
    # Dataset Management & Publication
    # ------------------------------------------------------------------
    if action == "dsets":
        universes = coordinator.db.list_universes(active_only=False)
        lines = ["📦 <b>Manage Datasets</b>", ""]
        rows = []
        for u in universes:
            latest = coordinator.db.get_latest_published_version(
                u.universe_id, kind=coordinator.config.dataset_kind
            )
            lines.append(
                f"• <b>{esc(u.name)}</b> — Latest: <code>{esc(latest or 'none')}</code>"
            )
            rows.append([_btn(f"Publish {u.name}", f"adm:dpub:{u.universe_id}", style=STYLE_PRIMARY)])
        rows.append([_btn("« Back to Admin", "adm:dash")])
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=clamp_text("\n".join(lines)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await answer_callback_safe(query)
        return

    if action == "dpub" and args:
        uid = args[0]
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn("Confirm Publish", f"adm:dpubc:{uid}", style=STYLE_SUCCESS),
                    _btn("Cancel", "adm:dsets"),
                ]
            ]
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"⚠️ Validate and publish a new immutable dataset for <code>{esc(uid)}</code>?\n\nExisting active and completed matches remain pinned to their original dataset versions.",
            reply_markup=kb,
        )
        await answer_callback_safe(query)
        return

    if action == "dpubc" and args:
        uid = args[0]
        ver = f"{uid}-{coordinator.config.dataset_kind.value[:4]}-{int(time.time())}"
        try:
            manifest, _health = coordinator.db.publish_dataset(
                universe_id=uid,
                dataset_version=ver,
                kind=coordinator.config.dataset_kind,
            )
            published_ver = manifest.dataset_version
            if coordinator.store:
                coordinator.store.record_admin_action(
                    actor_id=actor_id,
                    action="publish_dataset",
                    target_type="dataset",
                    target_id=published_ver,
                    details={"universe_id": uid, "count": len(manifest.records)},
                )
            text = f"✅ Published immutable dataset <code>{esc(published_ver)}</code> ({len(manifest.records)} characters)."
        except Exception as exc:
            text = f"⚠️ Publication blocked: {esc(exc)}"
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("« Back to Datasets", "adm:dsets")]]
            ),
        )
        await answer_callback_safe(query)
        return

    # ------------------------------------------------------------------
    # Active Matches & Administrative Termination
    # ------------------------------------------------------------------
    if action == "matches":
        active = list(coordinator.manager._matches.values())
        lines = [f"🎮 <b>Active Matches</b> ({len(active)})", ""]
        rows = []
        for m in active[:10]:
            lines.append(
                f"• <code>#{esc(m.match_id)}</code> — {esc(m.universe_id)} ({esc(m.game_mode)}, gen={m.generation})"
            )
            rows.append(
                [_btn(f"Terminate #{m.match_id[:10]}", f"adm:mterm:{m.match_id}", style=STYLE_DANGER)]
            )
        if not active:
            lines.append("No active matches.")
        rows.append([_btn("« Back to Admin", "adm:dash")])
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=clamp_text("\n".join(lines)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await answer_callback_safe(query)
        return

    if action == "mterm" and args:
        mid = args[0]
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn("Confirm Termination", f"adm:mtermc:{mid}", style=STYLE_DANGER),
                    _btn("Cancel", "adm:matches"),
                ]
            ]
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"⚠️ Administratively terminate match <code>#{esc(mid)}</code>?\n\nNo victory will be fabricated.",
            reply_markup=kb,
        )
        await answer_callback_safe(query)
        return

    if action == "mtermc" and args:
        mid = args[0]
        res = await coordinator.manager.terminate_match_externally(
            match_id=mid,
            reason=TerminationReason.ADMINISTRATIVE,
            source_label="admin_panel",
            caller_reference=f"admin:{actor_id}",
        )
        if res.accepted and res.match is not None:
            if coordinator.store:
                coordinator.store.record_admin_action(
                    actor_id=actor_id,
                    action="terminate_match",
                    target_type="match",
                    target_id=mid,
                    details={"reason": "administrative"},
                )
            await coordinator.sync_match_ui(
                res.match,
                last_action_line="Match terminated by administrator.",
                update_board=True,
                update_card=True,
            )
            msg_text = f"✅ Match <code>#{esc(mid)}</code> terminated."
        else:
            msg_text = f"⚠️ Could not terminate match: {esc(res.message)}"
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=msg_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("« Active Matches", "adm:matches")]]
            ),
        )
        await answer_callback_safe(query)
        return

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------
    if action == "bcast":
        coordinator.begin_broadcast_compose(actor_id)
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text="📢 <b>Broadcast</b>\n\nSend the broadcast message text in this private chat now, or click Cancel.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("✖ Cancel", "adm:bcanc", style=STYLE_DANGER)]]
            ),
        )
        await answer_callback_safe(query)
        return

    if action == "bcanc":
        coordinator.clear_broadcast_state(actor_id)
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text="📢 Broadcast cancelled.",
            reply_markup=_back_kb(),
        )
        await answer_callback_safe(query, "Cancelled.")
        return

    if action == "bsend":
        draft = coordinator.pop_broadcast_draft(actor_id)
        if not draft:
            await answer_callback_safe(query, "No broadcast draft found.", show_alert=True)
            return
        targets = coordinator.store.list_known_chats() if coordinator.store else []
        sent_ok = 0
        failed = 0
        for target_chat_id in targets:
            res_msg = await send_message_safe(
                coordinator.bot,
                chat_id=target_chat_id,
                text=f"📢 <b>Kayi Arena Announcement</b>\n\n{esc(draft)}",
            )
            if res_msg is not None:
                sent_ok += 1
            else:
                failed += 1
            await asyncio.sleep(0.05)

        if coordinator.store:
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="send_broadcast",
                target_type="broadcast",
                target_id=f"chats:{len(targets)}",
                details={"sent": sent_ok, "failed": failed},
            )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"📢 <b>Broadcast Complete</b>\n\nDelivered: <b>{sent_ok}</b>\nFailed/Blocked: <b>{failed}</b>",
            reply_markup=_back_kb(),
        )
        await answer_callback_safe(query, "Broadcast finished.")
        return

    # ------------------------------------------------------------------
    # Database Backup
    # ------------------------------------------------------------------
    if action == "backup":
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = Path("backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        state_ok, state_msg = (
            coordinator.store.integrity_check() if coordinator.store else (True, "in-memory")
        )
        state_bak = backup_dir / f"kayi_arena_state_{ts}.sqlite3"
        if coordinator.store is not None:
            coordinator.store.backup_to(state_bak)
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="database_backup",
                target_type="database",
                target_id=state_bak.name,
                details={"integrity": state_msg},
            )
        text = clamp_text(
            "\n".join(
                [
                    "💾 <b>Database Backup Complete</b>",
                    "",
                    f"Integrity check: <b>{'OK' if state_ok else 'ERROR'}</b> ({esc(state_msg)})",
                    f"Snapshot: <code>{esc(state_bak.name)}</code>",
                ]
            )
        )
        await edit_message_text_safe(
            coordinator.bot, chat_id=chat_id, message_id=msg_id, text=text, reply_markup=_back_kb()
        )
        await answer_callback_safe(query, "Backup created.")
        return

    # ------------------------------------------------------------------
    # Maintenance Mode
    # ------------------------------------------------------------------
    if action == "maint":
        currently_on = coordinator.is_maintenance_mode()
        verb = "Disable" if currently_on else "Enable"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _btn(f"Confirm {verb}", "adm:mconf", style=STYLE_DANGER if not currently_on else STYLE_SUCCESS),
                    _btn("Cancel", "adm:dash"),
                ]
            ]
        )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"🔧 <b>Maintenance Mode</b>\n\nCurrent state: <b>{'ON' if currently_on else 'OFF'}</b>\n\n{verb} maintenance mode?",
            reply_markup=kb,
        )
        await answer_callback_safe(query)
        return

    if action == "mconf":
        new_state = not coordinator.is_maintenance_mode()
        coordinator.set_maintenance_mode(new_state)
        if coordinator.store:
            coordinator.store.record_admin_action(
                actor_id=actor_id,
                action="set_maintenance_mode",
                target_type="setting",
                target_id="maintenance_mode",
                details={"enabled": new_state},
            )
        await edit_message_text_safe(
            coordinator.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"🔧 Maintenance mode is now <b>{'ON' if new_state else 'OFF'}</b>.",
            reply_markup=_back_kb(),
        )
        await answer_callback_safe(query, f"Maintenance {'enabled' if new_state else 'disabled'}.")
        return

    await answer_callback_safe(query)


def build_admin_router() -> Router:
    r = Router(name="kayi_arena_admin")
    r.message.register(cmd_admin, Command("admin"))
    r.message.register(
        handle_broadcast_input,
        F.chat.type == "private",
        F.text,
        ~F.text.startswith("/"),
    )
    r.callback_query.register(handle_admin_callback, F.data.startswith("adm:"))
    return r
