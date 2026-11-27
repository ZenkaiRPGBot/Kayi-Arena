# MongoDB Atlas M0 (512 MB) Storage & Capacity Report

## 1. Architecture Summary

Kayi Arena supports **SQLite** (`DB_BACKEND=sqlite`, default) and an optional **MongoDB Atlas** backend (`DB_BACKEND=mongodb`, `MONGODB_URI`, `MONGODB_DATABASE`).

- **Zero Binary Media in MongoDB:** Character images and welcome videos are **never** stored as binary blobs or GridFS documents in MongoDB. All media is standardized to `960x540` JPEG, uploaded once to a private Telegram `MEDIA_CHANNEL_ID`, and referenced solely by lightweight `telegram_file_id` + `image_hash` metadata in the `media_assets` collection.
- **SQLite Backward Compatibility:** Local development, unit tests, and zero-config Render deployments continue to default to SQLite without requiring any MongoDB credentials.

## 2. Estimated Document Sizes & Index Overhead

| Collection | Avg Document Size | Indexes | Est. 1,000 Docs | Est. 50,000 Docs |
| --- | --- | --- | --- | --- |
| `characters` | ~1.8 KB | `_id`, `(universe_id, status)` | ~1.8 MB | ~90 MB |
| `media_assets` | ~0.55 KB | `_id`, `character_id`, `(universe_id, upload_status)` | ~0.55 MB | ~27.5 MB |
| `matches` (active) | ~2.4 KB | `_id`, `(state, updated_at)` | ~2.4 MB | N/A (ephemeral active) |
| `match_history` | ~1.4 KB | `_id`, `(player_a_id, completed_at)`, `(player_b_id, completed_at)` | ~1.4 MB | ~70 MB |
| `challenges` | ~0.45 KB | `_id`, `(state, created_at)` | ~0.45 MB | ~22.5 MB |
| `player_profiles` | ~0.18 KB | `_id` | ~0.18 MB | ~9 MB |
| `known_chats` | ~0.16 KB | `_id` | ~0.16 MB | ~8 MB |
| `bot_settings` | ~0.12 KB | `_id` | < 0.01 MB | < 0.05 MB |
| `admin_audit_log` | ~0.35 KB | `_id`, `created_at` | ~0.35 MB | ~17.5 MB |

## 3. Atlas M0 (512 MB) Headroom Analysis

- **Initial Production Footprint (60–500 characters, 1,000 matches, 5,000 players):** **< 8 MB total** (including B-tree indexes), leaving **> 98%** of the 512 MB M0 quota free.
- **Scale Projection (2,000 characters, 100,000 historical matches, 50,000 players):** **~165–190 MB** including indexes (~37% of M0 quota).
- **Recommended Safeguards:**
  1. Periodically archive or TTL-prune `challenges` older than 7 days (`state != "open"`).
  2. Cap or TTL-prune `admin_audit_log` entries older than 180 days.
  3. Keep `MEDIA_CHANNEL_ID` as the sole binary store so MongoDB stores only ~550-byte `file_id` pointers.

## 4. Dry-Run Migration

Before enabling `DB_BACKEND=mongodb` in production, run `migrate_sqlite_to_mongo(sqlite_store, char_db=char_db, dry_run=True)` to inspect exact collection counts and estimated BSON bytes with zero writes.
