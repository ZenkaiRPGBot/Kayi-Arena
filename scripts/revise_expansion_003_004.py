"""Build the consolidated expansion evaluations with provenance.

Claude's original batch files are never modified.  This script embeds each
original record alongside the OpenCode-revised record and records every change.
"""

from __future__ import annotations

import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

ROOT = Path("data")
BATCHES = [
    ("003", ROOT / "naruto_batch_003_evaluations.json", ROOT / "naruto_batch_003_evaluations_revised.json"),
    ("004-A", ROOT / "naruto_batch_004_a_evaluations.json", ROOT / "naruto_batch_004_a_evaluations.json"),
    ("004-B", ROOT / "naruto_batch_004_b_evaluations.json", ROOT / "naruto_batch_004_b_evaluations.json"),
]

OUT_EVAL = ROOT / "naruto_expansion_003_004_evaluations.json"
OUT_LOG = ROOT / "naruto_expansion_003_004_change_log.json"

SEARCH = "search_result_summary"
CATALOGUE = "catalogue_metadata"


def lead(text: str, url: str | None, level: str = SEARCH, note: str | None = None) -> dict:
    return {
        "url": url,
        "lead": text,
        "check": "snippet_inspected" if level == SEARCH else level,
        "source_note": note or text,
        "verification_level": level,
    }


# ---------------------------------------------------------------------------
# 004-A revisions
# ---------------------------------------------------------------------------

REV_004_A: dict[str, dict] = {
    "Torune Aburame": {
        "power": 3,
        "justification": (
            "Root operative using rinkaichū nano-insects with one-touch lethality. "
            "The contact threat supports Attacker 4 and Assassin 4, but Power 4 implied "
            "Kage-level overall combat; secondary accounts place him at high-jōnin level "
            "and note Shino defeated him with specially bred counter-insects. Power lowered to 3."
        ),
        "review_flags_add": ["POWER_REVISED_TO_3", "HIGH_JONIN_NOT_KAGE"],
        "reason": "Power 4 overstated a contact-kill specialist as Kage-level; high-jōnin is the supported tier.",
        "source": "Narutopedia: Torune Aburame; Shino Aburame (rinkaichū counter); secondary power discussions",
    },
    "Ibiki Morino": {
        "evidence_leads": [
            lead(
                "Head of Konoha's Torture and Interrogation Force; master of physical and psychological interrogation.",
                "https://naruto.fandom.com/wiki/Ibiki_Morino",
                note="Narutopedia search summary; page not directly fetched",
            )
        ],
        "review_flags_add": ["STRATEGIST_INTERROGATION_INTERPRETATION"],
        "reason": "Strategist 4 is retained but explicitly interpreted as interrogation/intelligence planning, not battlefield command.",
        "source": "Narutopedia: Ibiki Morino",
    },
    "Nono Yakushi": {
        "fit": {"captain": 3},
        "justification": (
            "Jōnin and captain of the Konoha Medic Corps, later caretaker of the Konoha Orphanage; "
            "skilled medical-nin with excellent chakra control. Captain raised from 2 to 3 to reflect "
            "documented Medic Corps command. Healing remains 3: capable, not miracle-level."
        ),
        "evidence_leads": [
            lead(
                "Jōnin; captain of the Konoha Medic Corps; former Root Anbu; skilled medical-nin.",
                "https://naruto.fandom.com/wiki/Non%C5%8D_Yakushi",
                note="Narutopedia and Sportskeeda search summaries",
            )
        ],
        "review_flags_add": ["CAPTAIN_REVISED_TO_3"],
        "reason": "Documented captain of the Medic Corps supports Captain 3.",
        "source": "Narutopedia: Nonō Yakushi; Sportskeeda character profile",
    },
    "Mito Uzumaki": {
        "fit": {"support": 4},
        "justification": (
            "First Kurama jinchūriki and exceptional Uzumaki fūinjutsu user; sealed the entirety of "
            "Kurama within herself. Support raised from 3 to 4 for demonstrated top-tier sealing. "
            "Power remains 2 because no combat exchanges are documented."
        ),
        "evidence_leads": [
            lead(
                "Exceptional fūinjutsu; sealed Kurama within herself; powerful unique chakra.",
                "https://naruto.fandom.com/wiki/Mito_Uzumaki",
                note="Narutopedia search summary; page not directly fetched",
            )
        ],
        "review_flags_add": ["SUPPORT_REVISED_TO_4"],
        "reason": "Sealing Kurama is a demonstrated top-tier fūinjutsu feat and supports Support 4.",
        "source": "Narutopedia: Mito Uzumaki",
    },
    "Sakon and Ukon": {
        "evidence_leads_add": [
            lead(
                "Combined entry: molecular merge/parasitic possession kekkei genkai; Ukon can enter an opponent's body.",
                "https://naruto.fandom.com/wiki/Sakon_and_Ukon",
                note="Narutopedia search summary; debut chapter not independently verified",
            )
        ],
        "review_flags_add": ["COMBINED_PLAYABLE_ENTRY", "SOURCE_IDENTITIES_PRESERVED"],
        "reason": "Combined playable identity retained; both source identities preserved for mapping and owner review.",
        "source": "Narutopedia: Sakon and Ukon",
    },
    # ---- Held -> Draft conversions -------------------------------------
    "Yoroi Akado": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 2, "tank": 1, "assassin": 1, "support": 2, "healer": 0},
        "canonical_version": "Part I Yoroi Akadō: chakra absorption through physical contact; Chunin Exams arc.",
        "justification": (
            "Otogakure spy and former Konoha genin. Absorbs an opponent's physical and spiritual energy "
            "through direct contact, a genuine disruption tool in the Chunin Exams. Limited ranged and "
            "defensive showings keep Power at 2."
        ),
        "evidence_leads": [
            lead(
                "Chakra absorption through physical contact; Chunin Exams appearance.",
                "https://naruto.fandom.com/wiki/Yoroi_Akad%C5%8D",
                note="Narutopedia and Chakra Absorption Techniques search summaries",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "PRIMARY_MANGA_UNVERIFIED"],
        "reason": "Documented chakra-absorption ability supports a conservative Draft evaluation.",
        "source": "Narutopedia: Yoroi Akadō; Chakra Absorption Techniques",
    },
    "Misumi Tsurugi": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 2, "tank": 1, "assassin": 3, "support": 1, "healer": 0},
        "canonical_version": "Part I Misumi Tsurugi: Soft Physique Modification; Chunin Exams preliminaries.",
        "justification": (
            "Otogakure spy with surgical Soft Physique Modification: dislocates joints, stretches and "
            "bends his body for infiltration and grappling. Defeated by Kankurō in the preliminaries. "
            "Assassin 3 reflects infiltration and constriction; Power 2 reflects limited direct combat."
        ),
        "evidence_leads": [
            lead(
                "Soft Physique Modification; fought Kankurō in the Chunin Exams preliminaries.",
                "https://naruto.fandom.com/wiki/Misumi_Tsurugi",
                note="Narutopedia and ScreenRant search summaries",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "PRIMARY_MANGA_UNVERIFIED"],
        "reason": "Documented body-modification ability supports a conservative Draft evaluation.",
        "source": "Narutopedia: Misumi Tsurugi; Soft Physique Modification",
    },
    "Ko Hyuga": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 2, "tank": 1, "assassin": 1, "support": 2, "healer": 0},
        "canonical_version": "Part II Kō Hyūga: Byakugan and Gentle Fist; Hinata's bodyguard.",
        "justification": (
            "Branch-house Hyūga with the Byakugan and Gentle Fist. Entrusted with Hinata's protection, "
            "which implies competence, but individual combat showings are limited. Power 2, Attacker 2, "
            "Support 2 as a perception and guard package."
        ),
        "evidence_leads": [
            lead(
                "Byakugan and Gentle Fist; tasked with protecting Hinata.",
                "https://naruto.fandom.com/wiki/K%C5%8D_Hy%C5%ABga",
                note="Narutopedia search summary and derivative profile",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "LIMITED_INDIVIDUAL_FEATS"],
        "reason": "Clan abilities and bodyguard role provide a reasonable preliminary basis.",
        "source": "Narutopedia: Kō Hyūga",
    },
    "Iwashi Tatami": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 1, "tank": 1, "assassin": 0, "support": 3, "healer": 0},
        "canonical_version": "Part II Iwashi Tatami: chunin; Flying Thunder Formation Technique with a three-person squad.",
        "justification": (
            "Konoha chunin and member of the Fourth Hokage's guard. Uses the three-person Flying Thunder "
            "Formation Technique for space-time transport, a strong support utility. Individually a "
            "conventional chunin, so Power 2 and Support 3."
        ),
        "evidence_leads": [
            lead(
                "Chunin; Flying Thunder Formation Technique taught to the Hokage guard squad.",
                "https://naruto.fandom.com/wiki/Iwashi_Tatami",
                note="Narutopedia search summary; derivative profiles repeat the same claim",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "TEAM_TECHNIQUE_DEPENDENT"],
        "reason": "Documented space-time support technique provides a reasonable preliminary basis.",
        "source": "Narutopedia: Iwashi Tatami",
    },
    "Biwako Sarutobi": {
        "evaluation_status": "draft",
        "power": 1,
        "fit": {"captain": 1, "strategist": 1, "attacker": 0, "tank": 0, "assassin": 0, "support": 2, "healer": 3},
        "canonical_version": "Biwako Sarutobi: Konoha jōnin and medical-nin; pre-series, limited combat showings.",
        "justification": (
            "Konoha jōnin and accomplished medical-nin chosen to lead the midwife team for Kushina's "
            "delivery. Databook-derived summaries support the medical skill; no combat exchanges are "
            "documented, so Power 1 and Healer 3."
        ),
        "evidence_leads": [
            lead(
                "Jōnin and skilled medical-nin; led the midwife team for Kushina's delivery.",
                "https://naruto.fandom.com/wiki/Biwako_Sarutobi",
                note="Narutopedia and Sportskeeda search summaries; databook-derived",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "NO_COMBAT_SHOWINGS"],
        "reason": "Medical capability is documented by databook-derived secondary sources, not inferred from family role.",
        "source": "Narutopedia: Biwako Sarutobi; Sportskeeda character profile",
    },
    "Taji": {
        "evaluation_status": "draft",
        "power": 1,
        "fit": {"captain": 0, "strategist": 1, "attacker": 0, "tank": 0, "assassin": 2, "support": 2, "healer": 2},
        "canonical_version": "Taji: Konoha Anbu medical-nin; pre-series, limited combat showings.",
        "justification": (
            "Anbu medical-nin present at Kushina's delivery. Anbu membership implies infiltration and "
            "combat training; medical-nin status implies chakra-control training. No individual feats, "
            "so Power 1, Assassin 2, Support 2, Healer 2."
        ),
        "evidence_leads": [
            lead(
                "Anbu and medical-nin of Konohagakure; present at Kushina's delivery.",
                "https://naruto.fandom.com/wiki/Taji",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "low",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "NO_INDIVIDUAL_FEATS"],
        "reason": "Anbu and medical-nin roles are documented, supporting a conservative Draft evaluation.",
        "source": "Narutopedia: Taji",
    },
    "Tekka Uchiha": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 2, "attacker": 2, "tank": 1, "assassin": 1, "support": 1, "healer": 0},
        "canonical_version": "Part I Tekka Uchiha: Sharingan and sensor abilities; Konoha Military Police.",
        "justification": (
            "Uchiha police-force member who awakened the Sharingan; described as sensor-type. "
            "Sharingan perception and genjutsu support Strategist 2 and Attacker 2. No named "
            "signature technique, so Power 2."
        ),
        "evidence_leads": [
            lead(
                "Sharingan; Konoha Military Police; sensor-type.",
                "https://naruto.fandom.com/wiki/Tekka_Uchiha",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "GENERIC_SHARINGAN_KIT"],
        "reason": "Sharingan and police/sensor role are documented.",
        "source": "Narutopedia: Tekka Uchiha",
    },
    "Inabi Uchiha": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 2, "tank": 1, "assassin": 1, "support": 1, "healer": 0},
        "canonical_version": "Part I Inabi Uchiha: Sharingan; Konoha Military Police.",
        "justification": (
            "Uchiha police-force member with the Sharingan. Generic Uchiha perception and genjutsu "
            "support a conventional chunin-level combatant; no individual feats. Power 2."
        ),
        "evidence_leads": [
            lead(
                "Sharingan; Konoha Military Police.",
                "https://naruto.fandom.com/wiki/Inabi_Uchiha",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "GENERIC_SHARINGAN_KIT"],
        "reason": "Sharingan and police role are documented.",
        "source": "Narutopedia: Inabi Uchiha",
    },
    "Yashiro Uchiha": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 2, "tank": 1, "assassin": 1, "support": 1, "healer": 0},
        "canonical_version": "Part I Yashiro Uchiha: Sharingan; Konoha Military Police.",
        "justification": (
            "Uchiha police-force member with the Sharingan. Generic Uchiha perception and genjutsu "
            "support a conventional chunin-level combatant; no individual feats. Power 2."
        ),
        "evidence_leads": [
            lead(
                "Sharingan; Konoha Military Police.",
                "https://naruto.fandom.com/wiki/Yashiro_Uchiha",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "GENERIC_SHARINGAN_KIT"],
        "reason": "Sharingan and police role are documented.",
        "source": "Narutopedia: Yashiro Uchiha",
    },
    "Kagami Uchiha": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 1, "strategist": 2, "attacker": 3, "tank": 1, "assassin": 2, "support": 1, "healer": 0},
        "canonical_version": "Warring States/War-era Kagami Uchiha: Sharingan; member of Tobirama's unit.",
        "justification": (
            "Uchiha with powerful chakra and the Sharingan, selected for Tobirama's unit alongside "
            "Hiruzen and Danzō. The Sharingan and elite-unit selection support jōnin-level Power 3; "
            "no named signature technique, so the fit stays broad."
        ),
        "evidence_leads": [
            lead(
                "Sharingan; powerful chakra; member of Tobirama's unit.",
                "https://naruto.fandom.com/wiki/Kagami_Uchiha",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "NO_NAMED_TECHNIQUE"],
        "reason": "Sharingan and elite-unit service provide a reasonable preliminary basis.",
        "source": "Narutopedia: Kagami Uchiha",
    },
    "Torifu Akimichi": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 1, "strategist": 1, "attacker": 2, "tank": 3, "assassin": 0, "support": 1, "healer": 0},
        "canonical_version": "Warring States/War-era Torifu Akimichi: Akimichi calorie control, staff and shield.",
        "justification": (
            "Akimichi with notably high physical prowess, calorie-to-chakra conversion, and documented "
            "use of a staff and shield. Tank 3 reflects the defensive equipment and Akimichi durability; "
            "Power 2 because the full scope of his abilities is unrecorded."
        ),
        "evidence_leads": [
            lead(
                "Akimichi calorie control; high physical prowess; staff and shield.",
                "https://naruto.fandom.com/wiki/Torifu_Akimichi",
                note="Narutopedia and Sportskeeda search summaries",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "LIMITED_FEATS"],
        "reason": "Documented Akimichi abilities and equipment support a conservative Draft evaluation.",
        "source": "Narutopedia: Torifu Akimichi",
    },
}


# ---------------------------------------------------------------------------
# 004-B revisions
# ---------------------------------------------------------------------------

REV_004_B: dict[str, dict] = {
    "Kinkaku": {
        "evidence_leads_add": [
            lead(
                "Pseudo-jinchūriki: Nine-Tails chakra cloak and Version 2 form; Six Paths Treasured Tools.",
                "https://naruto.fandom.com/wiki/Kinkaku",
                note="Narutopedia search summary; war-arc Version 2 demonstration",
            )
        ],
        "review_flags_add": ["CONDITIONAL_TAILED_BEAST_POWER", "BORROWED_EQUIPMENT"],
        "reason": "Power 4 retained: Version 2 cloak is demonstrated on-panel in the war; tools treated as equipment, not extra Power.",
        "source": "Narutopedia: Kinkaku",
    },
    "Ginkaku": {
        "evidence_leads_add": [
            lead(
                "Nine-Tails chakra gained by consuming its flesh; Version 1/2 cloak documented but not demonstrated in the war.",
                "https://naruto.fandom.com/wiki/Ginkaku",
                note="Narutopedia search summary",
            )
        ],
        "review_flags_add": ["CONDITIONAL_TAILED_BEAST_POWER", "CLOAK_DOCUMENTED_NOT_DEMONSTRATED"],
        "reason": "Power 3 retained. The cloak is documented, but Kinkaku's on-panel Version 2 demonstration and broader feats justify one tier of separation.",
        "source": "Narutopedia: Ginkaku",
    },
    "Blue B": {
        "evidence_leads_add": [
            lead(
                "Former Eight-Tails jinchūriki; tailed-beast chakra cloak and chakra arms; fought Killer B while reanimated.",
                "https://naruto.fandom.com/wiki/Blue_B",
                note="Narutopedia search summary",
            )
        ],
        "review_flags_add": ["CONDITIONAL_TAILED_BEAST_POWER", "REANIMATED_SHOWING"],
        "reason": "Power 4 retained: cloak and chakra arms are demonstrated; horn restoration excluded.",
        "source": "Narutopedia: Blue B",
    },
    "Mifune": {
        "evidence_leads_add": [
            lead(
                "Master iaijutsu; speed prevents hand seals; leader of the Land of Iron samurai.",
                "https://naruto.fandom.com/wiki/Mifune",
                note="Narutopedia and Comics Central search summaries",
            )
        ],
        "review_flags_add": ["POWER_4_REVIEWED"],
        "reason": "Power 4 retained: quick-draw kenjutsu that disrupts hand seals and Kage Summit-level performance support it.",
        "source": "Narutopedia: Mifune",
    },
    "Kiri — Allied Shinobi Forces": {
        "canonical_version": "Allied Shinobi Forces Kiri: Kirigakure medical-nin; Fifth Division.",
        "evidence_leads_add": [
            lead(
                "Medical-nin from Kirigakure; serves in the Allied Shinobi Forces; heals wounded.",
                "https://naruto.fandom.com/wiki/Kiri_(ninja)",
                note="Narutopedia search summary; identity resolved to Kiri (ninja), not Kiri (villager)",
            )
        ],
        "review_flags_add": ["IDENTITY_RESOLVED", "HEALER_3_SINGLE_SCENE"],
        "reason": "Identity resolved to the Kirigakure medical-nin; the Boruto villager is a different person. Healer 3 retained.",
        "source": "Narutopedia: Kiri (ninja)",
    },
    "Zaji": {
        "canonical_version": "Fourth War Zaji: Konohagakure sensor; Fifth Division.",
        "evidence_leads_add": [
            lead(
                "Konoha sensor assigned to the Fifth Division; distinct from Zaji the gambler.",
                "https://naruto.fandom.com/wiki/Zaji",
                note="Narutopedia search summary; identity cross-checked against catalogue entry",
            )
        ],
        "review_flags_add": ["IDENTITY_RESOLVED", "DISAMBIGUATED_FROM_GAMBLER"],
        "reason": "Identity resolved to the Konoha sensor; the gambler is a separate catalogue entry.",
        "source": "Narutopedia: Zaji",
    },
    "Ameyuri Ringo": {
        "evidence_leads_add": [
            lead(
                "One of the Seven Ninja Swordsmen; wields the Kiba twin swords; lightning-enhanced blades.",
                "https://naruto.fandom.com/wiki/Ameyuri_Ringo",
                note="Narutopedia search summary",
            )
        ],
        "review_flags_add": ["EQUIPMENT_NOT_CREDITED_AS_POWER"],
        "reason": "Attacker 4 retained; named swords are equipment and are not converted into extra Power.",
        "source": "Narutopedia: Ameyuri Ringo; Seven Ninja Swordsmen",
    },
    # ---- Held -> Draft conversions -------------------------------------
    "Chukichi": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 1, "strategist": 3, "attacker": 2, "tank": 1, "assassin": 1, "support": 3, "healer": 0},
        "canonical_version": "Fourth War Chūkichi (reanimated): master sensor; Water Release and Hiding in Frost.",
        "justification": (
            "Renowned Kumogakure sensor able to detect subtle chakra signatures and minute details; "
            "also uses Water Release and the anime Hiding in Frost technique. Sensor mastery supports "
            "Strategist 3 and Support 3; Power 3 as a jōnin-level operative."
        ),
        "evidence_leads": [
            lead(
                "Master sensor; Water Release; Hiding in Frost (anime).",
                "https://naruto.fandom.com/wiki/Ch%C5%ABkichi",
                note="Narutopedia and Sportskeeda search summaries",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "ANIME_TECHNIQUE_FLAGGED"],
        "reason": "Documented sensor mastery supports a Draft evaluation.",
        "source": "Narutopedia: Chūkichi",
    },
    "Gari": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 0, "strategist": 1, "attacker": 3, "tank": 1, "assassin": 2, "support": 1, "healer": 0},
        "canonical_version": "Fourth War Gari (reanimated): Explosion Release kekkei genkai.",
        "justification": (
            "Iwagakure shinobi with Explosion Release, combining earth and lightning chakra. Uses "
            "Explosion Release: Landmine Fist and a defensive explosion technique. Jōnin-level Power 3; "
            "Attacker 3 and Assassin 2 for explosive close combat."
        ),
        "evidence_leads": [
            lead(
                "Explosion Release kekkei genkai; Landmine Fist; reanimated in the Fourth War.",
                "https://naruto.fandom.com/wiki/Gari",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "KEKKEI_GENKAI"],
        "reason": "Documented Explosion Release supports a Draft evaluation.",
        "source": "Narutopedia: Gari",
    },
    "Toroi": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 0, "strategist": 1, "attacker": 3, "tank": 1, "assassin": 1, "support": 1, "healer": 0},
        "canonical_version": "Fourth War Toroi (reanimated): Magnet Release shuriken.",
        "justification": (
            "Famed Kumogakure shinobi with Magnet Release. Magnetised shuriken make subsequent metal "
            "weapons nearly impossible to evade. Power 3 and Attacker 3 for a lethal ranged gimmick; "
            "limited versatility keeps other roles low."
        ),
        "evidence_leads": [
            lead(
                "Magnet Release; magnetised shuriken; famed Kumo shinobi.",
                "https://naruto.fandom.com/wiki/Toroi",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "KEKKEI_GENKAI"],
        "reason": "Documented Magnet Release supports a Draft evaluation.",
        "source": "Narutopedia: Toroi",
    },
    "Dodai": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 2, "strategist": 2, "attacker": 2, "tank": 3, "assassin": 0, "support": 3, "healer": 0},
        "canonical_version": "Fourth War Dodai: Lava Release rubber; Kumogakure jōnin and division commander.",
        "justification": (
            "Kumogakure jōnin and division commander with Lava Release in the form of durable, elastic "
            "rubber. Rubber walls and balls provide strong protection and battlefield control. Tank 3 "
            "and Support 3; Power 3."
        ),
        "evidence_leads": [
            lead(
                "Lava Release rubber; Rubber Wall; jōnin and division commander.",
                "https://naruto.fandom.com/wiki/Dodai",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "KEKKEI_GENKAI"],
        "reason": "Documented Lava Release and command role support a Draft evaluation.",
        "source": "Narutopedia: Dodai",
    },
    "Motoi": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 2, "attacker": 1, "tank": 1, "assassin": 0, "support": 3, "healer": 0},
        "canonical_version": "Part II Motoi: Kumogakure chunin tracker; island security and barrier duty.",
        "justification": (
            "Kumogakure chunin and expert tracker stationed on Genbu. Uses barrier/security duties and "
            "tracking rather than direct combat. Support 3 and Strategist 2; Power 2."
        ),
        "evidence_leads": [
            lead(
                "Chunin; expert tracker; stationed on Genbu; barrier duties.",
                "https://naruto.fandom.com/wiki/Motoi",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "NON_COMBAT_FOCUS"],
        "reason": "Documented tracking and security role support a conservative Draft evaluation.",
        "source": "Narutopedia: Motoi",
    },
    "Kakko": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 1, "strategist": 2, "attacker": 2, "tank": 2, "assassin": 1, "support": 1, "healer": 0},
        "canonical_version": "Third War Kakkō: Iwagakure jōnin; Earth and Yin Release.",
        "justification": (
            "Iwagakure jōnin who excelled in ninjutsu, taijutsu and genjutsu; used Earth Release and "
            "Yin Release. A well-rounded jōnin, so Power 3 with balanced but unspectacular role fits."
        ),
        "evidence_leads": [
            lead(
                "Jōnin; excels in ninjutsu, taijutsu and genjutsu; Earth and Yin Release.",
                "https://naruto.fandom.com/wiki/Kakk%C5%8D",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "GENERALIST"],
        "reason": "Documented all-round jōnin abilities support a Draft evaluation.",
        "source": "Narutopedia: Kakkō",
    },
    "Taiseki": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 2, "tank": 1, "assassin": 3, "support": 1, "healer": 0},
        "canonical_version": "Third War Taiseki: Hiding with Camouflage; Iwagakure shinobi.",
        "justification": (
            "Iwagakure shinobi who uses Hiding with Camouflage to become invisible by manipulating light. "
            "Invisibility supports Assassin 3; direct combat is conventional, so Power 2."
        ),
        "evidence_leads": [
            lead(
                "Hiding with Camouflage; light manipulation for invisibility.",
                "https://naruto.fandom.com/wiki/Taiseki",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY"],
        "reason": "Documented invisibility technique supports a Draft evaluation.",
        "source": "Narutopedia: Taiseki",
    },
    "Mahiru": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 0, "strategist": 1, "attacker": 3, "tank": 1, "assassin": 2, "support": 1, "healer": 0},
        "canonical_version": "Third War Mahiru: kenjutsu, Shadow Clone Technique, Earth Release.",
        "justification": (
            "Iwagakure shinobi skilled in kenjutsu and high-level ninjutsu, able to field up to twenty "
            "shadow clones and use Earth Release. Overpowered young Kakashi with speed and swordwork. "
            "Power 3, Attacker 3, Assassin 2."
        ),
        "evidence_leads": [
            lead(
                "Kenjutsu; up to twenty shadow clones; Earth Release; fast swordsman.",
                "https://naruto.fandom.com/wiki/Mahiru",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY"],
        "reason": "Documented clone and kenjutsu abilities support a Draft evaluation.",
        "source": "Narutopedia: Mahiru",
    },
    "Urakaku": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 1, "strategist": 1, "attacker": 2, "tank": 2, "assassin": 1, "support": 1, "healer": 0},
        "canonical_version": "Fourth War Urakaku: Land of Iron samurai; kenjutsu and Mifune's guard.",
        "justification": (
            "Land of Iron samurai and one of Mifune's right-hand men. Trained in kenjutsu with sharp "
            "reflexes; samurai armour supports Tank 2. No named technique, so Power 2."
        ),
        "evidence_leads": [
            lead(
                "Samurai; kenjutsu; sharp reflexes; Mifune's bodyguard.",
                "https://naruto.fandom.com/wiki/Urakaku",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "NO_NAMED_TECHNIQUE"],
        "reason": "Documented samurai training and guard role support a conservative Draft evaluation.",
        "source": "Narutopedia: Urakaku",
    },
    "Yura": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 1, "strategist": 2, "attacker": 2, "tank": 1, "assassin": 1, "support": 2, "healer": 0},
        "canonical_version": "Part II Yūra: Sunagakure jōnin and council member; Sasori's sleeper agent.",
        "justification": (
            "Sunagakure jōnin and trusted council member, selected by Sasori as a long-term sleeper "
            "agent and used to command Suna's defence. Power 3; Strategist 2 and Support 2 for command "
            "and coordination rather than a named combat technique."
        ),
        "evidence_leads": [
            lead(
                "Jōnin; Suna council member; Sasori's sleeper agent; commanded village defence.",
                "https://naruto.fandom.com/wiki/Y%C5%ABra",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "SLEEPER_AGENT"],
        "reason": "Documented rank and command role support a Draft evaluation.",
        "source": "Narutopedia: Yūra",
    },
    "Matsuri": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 0, "strategist": 1, "attacker": 2, "tank": 1, "assassin": 0, "support": 1, "healer": 0},
        "canonical_version": "Part II Matsuri: Sunagakure genin; jōhyō (anime) and above-average strength.",
        "justification": (
            "Sunagakure genin with above-average physical strength in the manga; in the anime she "
            "trains with the jōhyō, a rope-dart used for range control and defence. Power 2, Attacker 2."
        ),
        "evidence_leads": [
            lead(
                "Above-average strength; jōhyō training (anime).",
                "https://naruto.fandom.com/wiki/Matsuri",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "ANIME_TECHNIQUE_FLAGGED"],
        "reason": "Documented strength and weapon training support a conservative Draft evaluation.",
        "source": "Narutopedia: Matsuri",
    },
    "Maki": {
        "evaluation_status": "draft",
        "power": 2,
        "fit": {"captain": 1, "strategist": 2, "attacker": 1, "tank": 1, "assassin": 1, "support": 3, "healer": 0},
        "canonical_version": "Fourth War Maki: Sunagakure elite jōnin; cloth binding and sealing.",
        "justification": (
            "Elite Sunagakure kunoichi who manipulates binding cloth for restraint, concealment and "
            "protective domes, and serves on sealing teams. Support 3 and Strategist 2; Power 2 because "
            "her showings are support-oriented."
        ),
        "evidence_leads": [
            lead(
                "Elite jōnin; Cloth Binding Technique; Protective Cloth Dome; Sealing Team.",
                "https://naruto.fandom.com/wiki/Maki",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "SUPPORT_ORIENTED"],
        "reason": "Documented cloth and sealing abilities support a Draft evaluation.",
        "source": "Narutopedia: Maki",
    },
    "Shamon — Second Kazekage": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 1, "strategist": 3, "attacker": 2, "tank": 1, "assassin": 0, "support": 2, "healer": 0},
        "canonical_version": "Second Kazekage Shamon: puppet technique and tailed-beast research.",
        "justification": (
            "Second Kazekage who developed Sunagakure's puppet corps and researched tailed-beast "
            "military use. Deployed puppets in battle; exact skill is unrecorded. Kage rank supports "
            "Power 3, Strategist 3 for institutional and battlefield planning."
        ),
        "evidence_leads": [
            lead(
                "Second Kazekage; puppet deployment; tailed-beast research.",
                "https://naruto.fandom.com/wiki/Shamon",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "KAGE_RANK_CONSERVATIVE"],
        "reason": "Documented puppet development and Kage rank support a Draft evaluation.",
        "source": "Narutopedia: Shamon",
    },
    "Kamatari": {
        "evaluation_status": "draft",
        "power": 3,
        "fit": {"captain": 0, "strategist": 1, "attacker": 3, "tank": 1, "assassin": 1, "support": 1, "healer": 0},
        "canonical_version": "Kamatari: Temari's sickle-weasel summon; wind techniques and giant sickle.",
        "justification": (
            "Temari's one-eyed sickle-weasel summon, summoned through her Giant Folding Fan. Wields a "
            "sickle nearly its own length and generates the Sickle Weasel Technique's cutting wind. "
            "Power 3, Attacker 3 as a dedicated offensive summon."
        ),
        "evidence_leads": [
            lead(
                "Temari's sickle-weasel summon; giant sickle; Sickle Weasel Technique.",
                "https://naruto.fandom.com/wiki/Kamatari",
                note="Narutopedia search summary",
            )
        ],
        "confidence": "medium",
        "review_flags": ["HELD_TO_DRAFT", "SECONDARY_SOURCE_ONLY", "SUMMON_EQUIPMENT"],
        "reason": "Documented summon abilities support a Draft evaluation.",
        "source": "Narutopedia: Kamatari",
    },
}


def apply_revision(original: dict, revision: dict) -> tuple[dict, list[dict]]:
    revised = deepcopy(original)
    changes: list[dict] = []
    for field, value in revision.items():
        if field in {"reason", "source", "review_flags_add", "evidence_leads_add"}:
            continue
        if field == "fit":
            previous = revised.get("fit")
            revised["fit"] = {**previous, **value} if isinstance(previous, dict) else value
            changes.append({"field": "fit", "previous": previous, "proposed": revised["fit"]})
            continue
        previous = revised.get(field)
        revised[field] = value
        changes.append({"field": field, "previous": previous, "proposed": value})

    for flag in revision.get("review_flags_add", []):
        flags = revised.setdefault("review_flags", [])
        if flag not in flags:
            flags.append(flag)

    for item in revision.get("evidence_leads_add", []):
        revised.setdefault("evidence_leads", []).append(item)

    if "reason" in revision:
        for change in changes:
            change["reason"] = revision["reason"]
            change["source"] = revision.get("source")
    return revised, changes


def main() -> None:
    combined: list[dict] = []
    change_log: list[dict] = []

    batch_003_log = json.loads((ROOT / "naruto_batch_003_change_log.json").read_text(encoding="utf-8"))
    batch_003_changes: dict[str, list[dict]] = defaultdict(list)
    for entry in batch_003_log.get("changes", []):
        batch_003_changes[entry["character"]].append(
            {key: value for key, value in entry.items() if key != "character"}
        )

    for batch, original_path, revised_path in BATCHES:
        original_data = json.loads(original_path.read_text(encoding="utf-8"))
        revised_data = json.loads(revised_path.read_text(encoding="utf-8"))
        original_by_name = {c["name"]: c for c in original_data["characters"]}
        revised_by_name = {c["name"]: c for c in revised_data["characters"]}

        for name, original in original_by_name.items():
            revised = revised_by_name.get(name, original)
            changes: list[dict] = []

            if batch == "003":
                # Batch 003 has its own reviewed change log; embed those entries
                # per record so the combined file carries the same provenance.
                changes = batch_003_changes.get(name, [])
            else:
                overlay = REV_004_A if batch == "004-A" else REV_004_B
                if name in overlay:
                    revised, changes = apply_revision(original, overlay[name])
                    for change in changes:
                        change_log.append({"batch": batch, "character": name, **change})

            combined.append(
                {
                    "batch": batch,
                    "id": revised.get("id") or original.get("id"),
                    "name": name,
                    "source_file": str(original_path).replace("\\", "/"),
                    "original": original,
                    "revised": revised,
                    "changes": changes,
                }
            )

    # Merge the existing batch-003 change log entries.
    for entry in batch_003_log.get("changes", []):
        change_log.append({"batch": "003", **entry})

    out = {
        "universe_id": "naruto",
        "batch_id": "naruto-expansion-003-004",
        "mode": "consolidated_targeted_review",
        "evaluation_framework_version": "EVAL-FRAMEWORK-1.0",
        "scoring_version": "SCORE-1.0",
        "canonical_policy_version": "NARUTO-CANON-0.1",
        "rarity_version": "RARITY-0.2",
        "prepared_date": "2026-11-27",
        "batch_status": "draft",
        "provenance": {
            "original": "Claude bulk_preliminary evaluations, preserved unchanged in the source files",
            "revised": "OpenCode targeted review; see changes[] and the consolidated change log",
        },
        "counts": {
            "records": len(combined),
            "draft": sum(1 for r in combined if r["revised"].get("evaluation_status") == "draft"),
            "held": sum(1 for r in combined if r["revised"].get("evaluation_status") == "held"),
        },
        "characters": combined,
    }
    OUT_EVAL.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_LOG.write_text(
        json.dumps(
            {
                "universe_id": "naruto",
                "batch_id": "naruto-expansion-003-004",
                "prepared_date": "2026-11-27",
                "change_count": len(change_log),
                "changes": change_log,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT_EVAL} ({len(combined)} records)")
    print(f"wrote {OUT_LOG} ({len(change_log)} changes)")
    print("statuses:", out["counts"])


if __name__ == "__main__":
    main()
