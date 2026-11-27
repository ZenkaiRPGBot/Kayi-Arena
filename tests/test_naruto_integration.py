"""Automated tests for Initial Naruto Character Integration (60 records, batch admin, bootstrap, gameplay)."""

from __future__ import annotations

import datetime
import json
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from PIL import Image

from app.database import (
    CharacterDatabase,
    EvaluationStatus,
    HELD_NARUTO_NAMES,
    bootstrap_naruto_database,
    export_approved_snapshot,
    load_naruto_60_into_db,
)
from app.matches import MatchLifecycleStatus, MatchManager
from app.persistence import SqliteMatchStore
from app.scoring import DatasetKind, RatingInput, classify_rarity_v02, score_record
from app.telegram import BotConfig, create_dispatcher
from app.telegram.media import standardize_card_image


class MockBot:
    def __init__(self) -> None:
        self.id = 999999
        self.next_msg_id = 400
        self.sent_messages: list[dict[str, Any]] = []
        self.edited_messages: list[dict[str, Any]] = []
        self.callback_answers: list[dict[str, Any]] = []

    def _msg(self, chat_id: int | str, text: str = "") -> MagicMock:
        self.next_msg_id += 1
        m = MagicMock(spec=Message)
        m.message_id = self.next_msg_id
        m.chat = MagicMock(spec=Chat)
        m.chat.id = int(chat_id)
        m.chat.type = "private" if int(chat_id) > 0 else "supergroup"
        m.text = text
        return m

    async def send_message(self, **kwargs: Any) -> MagicMock:
        self.sent_messages.append(kwargs)
        return self._msg(kwargs["chat_id"], kwargs.get("text", ""))

    async def edit_message_text(self, **kwargs: Any) -> MagicMock:
        self.edited_messages.append(kwargs)
        return self._msg(kwargs["chat_id"], kwargs.get("text", ""))

    async def send_photo(self, **kwargs: Any) -> MagicMock:
        return self._msg(kwargs["chat_id"], kwargs.get("caption", ""))

    async def __call__(self, method: Any, **kwargs: Any) -> Any:
        from aiogram.methods import AnswerCallbackQuery

        if isinstance(method, AnswerCallbackQuery):
            self.callback_answers.append({"text": method.text, "show_alert": bool(method.show_alert)})
        return True


def _user(uid: int, name: str) -> User:
    return User(id=uid, is_bot=False, first_name=name, username=name.lower())


def _msg_upd(upd_id: int, *, chat_id: int, chat_type: str, user: User, text: str) -> Update:
    return Update(
        update_id=upd_id,
        message=Message(
            message_id=100 + upd_id,
            date=datetime.datetime.now(datetime.timezone.utc),
            chat=Chat(id=chat_id, type=chat_type),
            from_user=user,
            text=text,
        ),
    )


def _cb_upd(
    upd_id: int, *, chat_id: int, chat_type: str, msg_id: int, user: User, data: str
) -> Update:
    return Update(
        update_id=upd_id,
        callback_query=CallbackQuery(
            id=f"cb_{upd_id}",
            from_user=user,
            chat_instance="ci_1",
            message=Message(
                message_id=msg_id,
                date=datetime.datetime.now(datetime.timezone.utc),
                chat=Chat(id=chat_id, type=chat_type),
                from_user=_user(999999, "KayiArenaBot"),
                text="panel",
            ),
            data=data,
        ),
    )


def test_all_60_naruto_records_scores_rarities_and_images() -> None:
    dataset = json.loads(Path("data/naruto_evaluated_60_dataset.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path("data/naruto_initial_60_image_manifest.json").read_text(encoding="utf-8"))
    by_id = {c["candidate_id"]: c for c in manifest["characters"]}

    chars = dataset["characters"]
    assert len(chars) == 60
    held = [c["name"] for c in chars if c.get("held") or c.get("evaluation_status") == "held"]
    assert set(held) == HELD_NARUTO_NAMES
    assert len(held) == 7

    for c in chars:
        out = score_record(RatingInput(character_id=c["character_id"], power=c["power"], fit=c["fit"]))
        assert dict(out.scores) == c["scores"]
        rar = classify_rarity_v02(
            power=c["power"], role_fits=c["fit"], role_scores=out.scores, apply_naruto_healer_floor=True
        )
        assert rar.final_rarity == c["rarity"]
        m_entry = by_id[c["character_id"]]
        valid_imgs = [i for i in m_entry.get("images", []) if i.get("status") == "valid"]
        assert valid_imgs, f"Missing valid image for {c['name']}"
        assert valid_imgs[0]["url"].startswith("https://")


def test_standardize_card_image_preserves_aspect_ratio_without_stretching() -> None:
    buf = BytesIO()
    Image.new("RGB", (400, 800), (200, 50, 50)).save(buf, format="PNG")
    out_bytes = standardize_card_image(buf.getvalue(), rarity="Legendary")
    with Image.open(BytesIO(out_bytes)) as out_img:
        assert out_img.size == (960, 540)


def test_naruto_loader_bootstrap_and_testing_dataset_isolation(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    summary = load_naruto_60_into_db(db, publish_testing_dataset=False)
    assert summary.total_loaded == 60
    assert summary.draft_count == 53
    assert summary.held_count == 7
    # Production dataset must NOT be auto-published
    assert db.get_latest_published_version("naruto", kind=DatasetKind.PRODUCTION) is None
    assert not db.list_characters(universe_id="naruto", status=EvaluationStatus.APPROVED)

    # Testing dataset approves ONLY the 53 non-held records under DatasetKind.TEST
    test_summary = load_naruto_60_into_db(db, publish_testing_dataset=True)
    assert test_summary.approved_for_testing == 53
    assert test_summary.published_testing_version == "naruto-prelim-test-v1"
    assert db.get_latest_published_version("naruto", kind=DatasetKind.PRODUCTION) is None
    for ch in db.list_characters(universe_id="naruto", status=EvaluationStatus.APPROVED):
        assert ch.name not in HELD_NARUTO_NAMES

    # Snapshot export & fresh bootstrap after ephemeral filesystem wipe
    snap_path = tmp_path / "approved_snapshot.json"
    # Simulate owner-approved production dataset
    db.publish_dataset("naruto", "naruto-prod-v1", kind=DatasetKind.PRODUCTION)
    export_approved_snapshot(db, universe_id="naruto", output_path=snap_path)
    db.close()

    fresh_db = CharacterDatabase(tmp_path / "fresh_chars.sqlite3")
    restored = bootstrap_naruto_database(
        fresh_db, dataset_kind=DatasetKind.PRODUCTION, snapshot_path=snap_path
    )
    assert restored.published_production_version == "naruto-prod-v1"
    assert len(fresh_db.list_characters(universe_id="naruto", status=EvaluationStatus.APPROVED)) == 53
    fresh_db.close()


@pytest.mark.asyncio
async def test_tester_restriction_batch_admin_and_full_naruto_gameplay(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    bootstrap_naruto_database(db, dataset_kind=DatasetKind.TEST)
    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    mgr = MatchManager(db, dataset_kind=DatasetKind.TEST, store=store)
    bot = MockBot()
    cfg = BotConfig(
        bot_token="tok",
        owner_id=1000,
        authorized_tester_ids=(201, 202),
        dataset_kind=DatasetKind.TEST,
    )
    dp, coordinator = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr, store=store)

    outsider = _user(999, "Outsider")
    p1 = _user(201, "Tester1")
    p2 = _user(202, "Tester2")

    # Unauthorized user blocked from testing dataset in group
    await dp.feed_update(bot, _msg_upd(1, chat_id=-1001, chat_type="supergroup", user=outsider, text="/arena"))
    assert "restricted to authorized testers" in bot.sent_messages[-1]["text"]

    # Authorized testers play full Naruto draft on testing dataset
    _, res = await mgr.handle_draft_command(
        player_id="201", chat_id="-1001", universe_arg="naruto", game_mode="ranked"
    )
    assert res and res.accepted and res.challenge
    acc = await mgr.accept_challenge(challenge_id=res.challenge.challenge_id, player_id="202")
    match = acc.match
    assert match is not None

    # Exercise skip + all 14 assignments
    active = match.draft_snapshot.active_player_id
    sh0 = await mgr.shuffle_match(
        match_id=match.match_id,
        player_id=active,
        expected_revision=match.draft_snapshot.revision,
        expected_generation=match.generation,
    )
    assert sh0.accepted and sh0.match
    sk0 = await mgr.skip_match_character(
        match_id=match.match_id,
        player_id=active,
        expected_revision=sh0.match.draft_snapshot.revision,
        expected_generation=sh0.match.generation,
    )
    assert sk0.accepted and sk0.match
    match = sk0.match

    while match.status is MatchLifecycleStatus.DRAFTING:
        actor = match.draft_snapshot.active_player_id
        sh = await mgr.shuffle_match(
            match_id=match.match_id,
            player_id=actor,
            expected_revision=match.draft_snapshot.revision,
            expected_generation=match.generation,
        )
        assert sh.accepted and sh.match
        role = match.public_view.remaining_roles[actor][0]
        as_res = await mgr.assign_match_role(
            match_id=match.match_id,
            player_id=actor,
            role=role,
            expected_revision=sh.match.draft_snapshot.revision,
            expected_generation=sh.match.generation,
        )
        assert as_res.accepted and as_res.match
        match = as_res.match

    assert match.status is MatchLifecycleStatus.COMPLETED
    assert match.outcome is not None and match.outcome.resolution is not None

    # Test batch admin submit & approve on a fresh production DB (preserving 7 Held)
    prod_db = CharacterDatabase(tmp_path / "prod.sqlite3")
    load_naruto_60_into_db(prod_db, publish_testing_dataset=False)
    prod_store = SqliteMatchStore(tmp_path / "prod_state.sqlite3")
    prod_bot = MockBot()
    prod_dp, prod_coord = create_dispatcher(
        bot=prod_bot,
        config=BotConfig(bot_token="tok", owner_id=1000, dataset_kind=DatasetKind.PRODUCTION),
        db=prod_db,
        store=prod_store,
    )
    admin = _user(1000, "Owner")
    await prod_dp.feed_update(prod_bot, _msg_upd(1, chat_id=1000, chat_type="private", user=admin, text="/admin"))
    panel_id = 400 + len(prod_bot.sent_messages)

    await prod_dp.feed_update(
        prod_bot, _cb_upd(2, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:chsuball:naruto")
    )
    assert "Submitted <b>53</b>" in prod_bot.edited_messages[-1]["text"]
    assert "Held preserved: <b>7</b>" in prod_bot.edited_messages[-1]["text"]

    await prod_dp.feed_update(
        prod_bot, _cb_upd(3, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:chappallc:naruto")
    )
    assert "Batch-approved <b>53</b>" in prod_bot.edited_messages[-1]["text"]
    assert len(prod_db.list_characters(universe_id="naruto", status=EvaluationStatus.APPROVED)) == 53
    assert len(prod_db.list_characters(universe_id="naruto", status=EvaluationStatus.DRAFT)) == 7

    await prod_coord.shutdown()
    await coordinator.shutdown()
    prod_store.close()
    prod_db.close()
    store.close()
    db.close()
