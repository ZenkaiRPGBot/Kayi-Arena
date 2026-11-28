# Naruto Batch 005 — Final Integration and Publication Preparation Report

## 1. Objective and status

- Repository: `Kayi-Arena`
- Content branch: `content/naruto-batch-005` (audited commit `539be7b`)
- Target branch: `main`
- Prepared: 2026-11-28
- Status: **pending owner review**. No approval or publication was performed.

This report completes integration preparation for Naruto Batch 005. Research, numerical evaluation, independent audit, cumulative balance verification, simulation-integrity correction and `KA-IMPORT-1.0` compatibility validation were already completed and are not repeated here.

## 2. Actual production roster count

- Live database path checked: `data\kayi_arena.sqlite3`
- Live database available: **False**
- Verified production character count: **unavailable**
- Current dataset version: **unavailable**
- Pending character count: **unavailable**
- Existing Held records in live DB: **unavailable**
- Limitation: No live SQLite database file found in the workspace; production counts are unavailable.
- Reconstructed non-Held draft roster (initial 60 + Batches 003–004): **184** (not verified published)
- Batch 005 ID overlap with reconstructed roster: **0**

## 3. Batch 005 import results

- Candidates audited: 62
- Importable audited evaluations: 52
- Importable evaluations: 52
- Held candidates: 10
- Documented rating changes: 7
- Catalogue candidates imported to staging: 62
- Evaluation records updated in staging: 52
- Duplicate catalogue import blocked: True
- Repeated evaluation import created no duplicate characters: True
- Imported ratings match audited values: True
- Staging database only; live production database was not modified.

## 4. Held or blocked records

- `dattebayo:901` — Nishi (sensor): BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:435` — Hanabi Hyūga: BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:1413` — Yurui: BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:846` — Mugino: BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:1068` — Makinami Senka: BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:1069` — Sazanami Senka: BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:1070` — Takanami Senka: BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:1377` — Yodo: BORUTO_ERA_ELIGIBILITY_UNRESOLVED
- `dattebayo:801` — Hamaki Mimura: BORROWED_EQUIPMENT_ONLY
- `dattebayo:434` — Hyūga Elder: INSUFFICIENT_DEMONSTRATED_ABILITY

All 10 Held candidates remain excluded from the importable evaluation package and from publication. No placeholder ratings were assigned.

## 5. Artwork review

- Batch 005 catalogue candidates: 62
- Technically valid images: 63
- Candidates with valid artwork: 62/62
- Invalid: 0; missing: 0; duplicates: 0
- Technical image validity only checks format, dimensions and checksum. Visual identity verification, canonical-version accuracy and publication permission remain unresolved and require owner review.

## 6. Characters lacking meaningful specialist roles

The corrected cumulative comparison identified 33 characters with all seven Role Fits at 1 or below. All are Batch 005 additions. They are flagged for owner consideration, not automatically excluded and not inflated.

- Suzaku Nara
- Shitō Akimichi
- Mozuku
- Daen Nara
- Kasuga Nara
- Maen Nara
- Gaku Inuzuka
- Urushi
- Yūgao Uzuki
- Kokage Yanagikage
- Tonbo Tobitake
- Furui
- Isago
- Saisu Kamano
- Shinobu Mibu
- Mizunoto
- Bunpuku
- Sabu
- Mitate
- Ugatsu
- Mitoku
- Kaiza
- Tessen Togeito
- Kaji
- Yoshiteru
- Mawashi Dokuraku
- Genzō
- Shinku Yūhi
- Tajiki
- Natori
- Oyone
- Kumadori
- Yurika

## 7. Expected roster count after publication

- Reconstructed non-Held draft roster: 184
- Batch 005 importable records: 52
- Expected reconstructed roster after approval/publication: **236**
- This is not a verified production count because no live production snapshot was available.

## 8. Dataset integrity verification

- Historic evaluated dataset files were read but not modified by this integration preparation.
- Existing published dataset snapshots remain immutable.
- Active matches remain pinned to their original dataset versions; no dataset version was published or replaced.
- No match results, scores or character snapshots were altered.

## 9. Validation and regression results

- Focused integration tests: passed.
- Complete repository regression suite: passed.
- Arena UI, UI 2.1 and Arena Logs 2.0 functionality preserved (no gameplay source files were overwritten by older content-branch versions).
- Simulation integrity tests: passed with role-specific Fit 0 score maxima.

## 10. Commit and deployment status

- Content audited commit: `539be7b`
- Integration commit: see final commit on `main`.
- Deployment status: **not deployed**; no live approval, publication or universe activation was performed.

## 11. Exact owner-side approval and publication instructions

1. Open Telegram as an authorized owner/admin and run `/admin` in a private chat.
2. Enter **Character Review** (`adm:chars`), select `naruto`, filter to **Review**, and confirm the 52 Batch 005 records are present with the audited ratings.
3. Verify the 10 Held records remain unscheduled/unrated. Do not approve them.
4. Use **Submit Non-Held Drafts** (`adm:chsuball:naruto`) only for the 52 eligible records if they are still in Draft, then use **Batch Approve Review** (`adm:chappall:naruto`) with the Batch 005 filter.
5. Confirm each individual approval prompt or the batch-approval confirmation. Admin actions are audit-logged.
6. Open **Manage Datasets** (`adm:dsets`) and choose **Publish Prod (Naruto)** (`adm:dpub:naruto`), then **Confirm Publish** (`adm:dpubc:naruto`).
7. Verify the new immutable dataset version reports the expected approved roster count. Existing active and completed matches remain pinned to their original dataset versions.
8. Do not activate any additional universe or Batch 006 content as part of this approval.
