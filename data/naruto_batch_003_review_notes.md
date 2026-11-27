# Naruto Batch 003 — Review Notes (Track A)

Status: **DRAFT, nothing approved.** 50 characters: 47 Draft, 3 Held (Dan Kato, White Zetsu, Mabui). Standards, SCORE-1.0 and RARITY-0.2 unchanged. Rarity and role scores are not in the JSON.

## 1. What was and was not verified

- **No character was checked against the primary manga.** I searched secondary sources for the uncertain cases only: Rin Nohara, Dan Kato, Karin, Shikaku and Darui (plus a weak lead on C).
- Those leads are marked `secondary_source_confirmed`. All other leads are `recollection_only` and located to arc level; I give no chapter numbers I could not confirm.
- Treat the ratings as a preliminary draft. Independent review must verify them before any approval.

## 2. Shape of the batch

- Power: no Power 5; Power 4 for Rasa, Kimimaro and Darui; Power 3 for 32; Power 2 for 14; Power 1 for Mabui (placeholder).
- No Fit 5 except Shikaku's Strategist (flagged `FIT_5_REVIEW`).
- Healer: Shizune, Karin and Rin Nohara at 3; Ino and C at 2. **No Healer above 3**, so this batch adds depth but no top-tier healer.
- Support specialists: Ino and Inoichi at 4; Yamato, Karin at 4.

## 3. Eligibility, aliases and duplicate identities

| Item | Handling |
|---|---|
| White Zetsu | **Held.** Unclear whether the entry is the clone army or one individual; mindless-clone eligibility question; related to existing Black Zetsu |
| Dan Kato | **Held.** Flashback-only with no demonstrated abilities |
| Mabui | **Held.** No combat or specialist abilities established |
| Yamato | Alias Tenzo; flagged `ALIAS_TENZO` |
| Rasa | Same person as the Fourth Kazekage; do not duplicate the existing Third Kazekage record |
| Yagura | Alias Fourth Mizukage; evidence mostly under Obito's control |
| C | Short identity ("C"); canonical name and aliases need OpenCode confirmation (`ALIAS_IDENTITY_CHECK`) |
| Jinchuriki hosts (Yugito, Roshi, Han, Utakata, Fu) | Separate from their beasts, which already exist or remain separate. Shared events are flagged and credited only to the performer |

## 4. Disputed evaluations

- **Shikaku, Strategist 5.** Chief Strategist of the Alliance is confirmed by secondary sources, and the formation redesign supports a second demonstration. Needs primary-source review.
- **Ino and Inoichi, Support 4.** Both rely on the Alliance mind-relay network; each could be 5, but they may double-count the same role. Review together.
- **Karin, Healer 3.** Heal Bite restores wounds of others (secondary sources, ch. 663 cited) but is costly and limited, so not higher. Alternative 4 if war-scale use is verified.
- **Rin Nohara, Healer 3.** One flashback demonstration (the eye transplant) and a medic role. Alternative 2. Jinchuriki state excluded.
- **Hidan, Tank 4.** His immortality is his own ability, but the policy for it is not settled. If immortality counts only as Conditional or is excluded, Tank drops to 3.
- **Neji, Tank 4.** Rests on his final interception, which is fatal and a one-time demonstration. Alternative 3.
- **Choji and Anko.** Fatal pill state and Twin Snake Mutual Death are excluded; ratings reflect the non-fatal versions.
- **Kimimaro, Power 4.** Illness limits stamina; the sustained-state question is unresolved. Alternative 3.
- **Rasa and Pakura.** Edo-only evidence; both low confidence.
- **Yagura.** Evidence is largely under Obito's control; treated as an inferred uncontrolled prime.

## 5. Consistency comparisons

- **Sound Four and Kimimaro:** Kimimaro Power 4, the Four at 3 with Attacker 3. Consistent with Orochimaru's ranking of them.
- **Medics (Shizune, Karin, Rin, C, Ino):** one rule, restoration of others only. Consistent with Tsunade 5, Sakura 4, Kabuto 3 from the earlier batches.
- **Division commanders (Darui, Shikamaru, Gaara, Kakashi):** Captain 4 for Darui (confirmed First Division commander) matches Gaara's confirmed division command; Shikamaru and Kakashi stay at 3.
- **Hyuga pair:** Neji Tank 4 versus Hinata 3; both intercepted for Naruto, but Neji's was the more demanding case.
- **Cloud team (Darui, Omoi, Karui, C, Mabui):** thin evidence below Darui, so most are low confidence.
- **Jinchuriki hosts:** Power 3 for hosts with Conditional beast access, 2 for Fu; separate from the beasts' own ratings.

## 6. Unresolved policy questions (not decided here)

1. Whether Hidan's ritual immortality counts as Core, Conditional or excluded.
2. Whether a one-time sacrificial interception (Neji) counts as Tank evidence.
3. Treatment of unwilling or controlled jinchuriki states (Rin, Yagura).
4. How to treat a character with a chronic illness in the selected version (Kimimaro).
5. Whether mindless clone armies (White Zetsu) are eligible.

## 7. For OpenCode

- Match using `id`, `canonical_name` and `aliases`; flags with `ALIAS_`, `DUPLICATE_IDENTITY_AMBIGUITY` and `RELATED_TO_` need identity review before import.
- Held records should not be imported as playable until the owner decides.
- This file does not replace the earlier revised 60-character review; compare that separately.
