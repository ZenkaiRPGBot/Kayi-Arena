# Kayi Arena — Engineering & Agent Instructions

## Mandatory Development Workflow

For every future development assignment in this repository, follow this exact sequence:

1. **Implementation** — Write modular, type-safe code preserving approved gameplay rules, character evaluations, and UI layouts.
2. **Tests** — Add or update targeted unit and integration tests for all new behavior and bug fixes.
3. **CodeRabbit Review** — Run CodeRabbit CLI review on Windows (locate `coderabbit` in `PATH` or `%LOCALAPPDATA%\Programs\coderabbit\coderabbit.exe`):
   - Verify auth: `"<cli_path>" auth status --agent`
   - Review changes: `"<cli_path>" review --agent --base-commit <commit>` (or `--uncommitted`)
4. **Fix Findings** — Resolve all confirmed `critical`, `major`, and relevant `minor` findings without weakening security or bypassing validation.
5. **Regression Tests** — Re-run the full `pytest tests -v` suite (and live MongoDB Atlas checks when database code changes) after all fixes.
6. **Final Review** — Confirm clean `git status`, zero secret exposure, and accurate verification output.
7. **Commit** — Commit cleanly with a descriptive conventional commit message.
8. **GitHub Push** — Push verified updates to `main` (or the requested branch).

## Security & Secret Protection

- **Never** commit or include `.env`, bot tokens, `MONGODB_URI`, `WEBHOOK_SECRET`, SQLite database files (`*.sqlite3`), or database dumps in Git commits or external review scopes.
- Keep `MONGODB_URI`, `BOT_TOKEN`, `OWNER_ID`, `ADMIN_IDS`, `MEDIA_CHANNEL_ID`, and `WEBHOOK_SECRET` as `sync: false` in `render.yaml`.
- Preserve SSRF protection in `app/telegram/media.py` (`validate_media_url`), admin-only private-chat checks in `app/telegram/handlers/admin.py`, and `X-Telegram-Bot-Api-Secret-Token` enforcement in `app/telegram/web.py`.
