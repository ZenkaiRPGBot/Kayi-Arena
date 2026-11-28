import json,sys,re,collections
sys.path.insert(0,'/home/claude/b5')
from fit import FIT
U='/mnt/user-data/uploads/'; O='/mnt/user-data/outputs/'
R=json.load(open(U+'naruto_batch_005_research.json'))['candidates']
CAT={c.get('candidate_id',c.get('id')):c for c in json.load(open(U+'naruto_batch_005_catalogue.json'))['candidates']}
ROLES=["captain","strategist","attacker","tank","assassin","support","healer"]
COEF=dict(captain=12,strategist=17,attacker=10,tank=10,assassin=13,support=17,healer=17)
# Pass B power (assigned after Fit was frozen)
P={879:2,441:1,724:2,1370:2,901:1,46:1,435:2,841:1,871:1,874:1,875:1,1094:2,1413:2,464:1,1332:1,1337:2,122:3,338:2,779:2,846:2,1374:1,210:2,1068:1,1069:1,1070:1,1232:2,1377:2,103:1,213:1,251:2,473:1,563:1,787:1,801:1,820:2,905:2,1428:2,146:3,1350:2,131:1,1000:2,810:1,1005:1,1319:1,812:1,434:1,544:1,1236:1,545:1,1389:1,203:1,1264:1,305:1,1398:1,1176:1,729:1,882:1,948:1,706:1,1410:1,987:1,1057:1}
POW={f"dattebayo:{k}":v for k,v in P.items()}
CSET={724,435,901,1413,1337,846,1068,1069,1070,1377,251,131}
ASET={1370,46,1236,563,338,779,905,1428,1350,1000,810,1005,812,1319,1176,305,1332,1232}
def num(i): return int(i.split(':')[1])
def grade(i): n=num(i); return 'C' if n in CSET else ('A' if n in ASET else 'B')
CAP={'A':4,'B':3,'C':2}
FIELD=dict(captain='leadership',strategist='tactics',attacker='offense',tank='defense_durability',assassin='stealth_infiltration_assassination',support='support_control',healer='medical_healing',power='combat_effectiveness')
def clean(s,n=230):
    s=re.sub(r'^unknown:.*','',s or '').strip()
    if len(s)>n: s=s[:n].rsplit(' ',1)[0]+'…'
    return s
def summ(c,t):
    cs=c['capability_summary']; s=clean(cs.get(FIELD[t]))
    if not s: s=clean(cs.get('significant_achievements'))
    if not s and c['demonstrated_abilities']: s=clean(c['demonstrated_abilities'][0]['description'])
    return s
ALT={724:"Power 3-4 if anime-only Kiba/natural-lightning feats were admitted",210:"Power 4 if Eight Gates (fatal technique) were admitted as sustainable",122:"Power 4 (survived Eight Gates formation; major kills) pending manga verification",146:"Power 4 pending chapter-level check of Hidan/Kakuzu fight",435:"Power 3 if movie/anime feats were admitted",1337:"Power 3 if anime kenjutsu feats were admitted",846:"Power 3 pending Boruto manga check",
 871:"Power 2 (jonin Nara)",874:"Power 2",875:"Power 2",1236:"Power 2 (tokubetsu jonin)",46:"Power 2 (jonin)",1398:"Power 2 (jonin instructor)",103:"Power 2",1389:"Power 2",464:"Power 2",33:"",801:"Power 2",
 905:"Support 3",1001:"",987:"Healer 3",1057:"Healer 3",729:"Support 4 (greatest sensory ability in Kirigakure per databook)"}
ALT={ (k if isinstance(k,int) else k):v for k,v in ALT.items() if v}
EXCL={210:["Eight Gates Released Formation excluded: fatal, one-time technique that ended his life (CANON-0.1 section 3.4 / X class)","Anime-only kills of four swordsmen"],
1094:["Impure World Reincarnation regeneration and explosive-clay payload excluded (reanimation-specific)"],
122:["Kubikiribōchō regeneration treated as equipment-dependent; anime-only clones/mist not relied on"],
724:["Anime-only feats (episodes 154-157) used only as capped C-grade evidence"],
131:["Shukaku's sand/chakra not attributed to host; anime teakettle sealing not relied on"],
435:["Anime/movie-only demonstrations used only as capped C-grade evidence"],
1337:["Anime-only kenjutsu and medical expansions used only as capped C-grade evidence"],
1413:["Boruto-era anime evidence used only as capped C-grade evidence"],
846:["Anime-only Rock Gun technique excluded; cave-collapse suicide measure not counted as sustainable"],
464:["Speculated Inuzuka techniques excluded (source says not demonstrated)"],
1332:["Naruto Mobile taijutsu/shurikenjutsu excluded (game material)"],
1389:["Presumed kenjutsu proficiency excluded"],1350:["Databook iai-nuki-from-seiza claim not shown; excluded"],
1236:[],251:["Anime Lightning Release movement halt used only as capped C-grade evidence"],
1000:["Naruto Mobile limited-ability profile not used as evidence"],}
extra=collections.defaultdict(list)
def addf(n,*f): extra[n]+=list(f)
for n in (724,435,901,1413,1337,846,1068,1069,1070,1377,251,131): addf(n,"ADAPTATION_OR_ERA_EVIDENCE","INDEPENDENT_REVIEW")
for n in (901,1413,846,1068,1069,1070,1377,435): addf(n,"BORUTO_ERA_ECV")
for n in (210,): addf(n,"DISPUTED_ECV_FATAL_TECHNIQUE","INDEPENDENT_REVIEW")
for n in (122,146,724): addf(n,"POWER_3_ALT_4_REVIEW")
for n in (131,): addf(n,"BORROWED_BEAST_POWER_NOT_ATTRIBUTED")
for n in (879,871,874,875,1094): addf(n,"UNCITED_CHAPTER_REFERENCES")
for n in (729,1005,1264,441,901): addf(n,"SENSOR_SUPPORT_TEMPLATE_CHECK")
for n in (948,706): addf(n,"HEALER_1_INFERRED_MEDICAL_SKILL")
for n in (987,1057): addf(n,"HEALER_2_NEEDS_REVIEW")
ev=[];det={}
for c in R:
    i=c['candidate_id']; n=num(i); g=grade(i); f=FIT[i]; fit=dict(zip(ROLES,f)); p=POW[i]
    assert p<=CAP[g] and all(v<=CAP[g] for v in f),(i,g)
    E=[{"target":"power","grade":g,"source_ref":f"naruto_batch_005_research.json:{i}","summary":summ(c,'power')}]
    for r in ROLES:
        if fit[r]>0: E.append({"target":r,"grade":g,"source_ref":f"naruto_batch_005_research.json:{i}","summary":summ(c,r)})
    urls=[c['source_url']]+[s['url'] for s in c['supporting_evidence'] if s['url'] not in [c['source_url']]]
    ev.append({"character_id":i,"power":p,"fit":fit,"evidence":E,"source_references":list(dict.fromkeys(urls)),"revision_ref":f"claude-batch-005-{len(ev)+1:03d}","submit_for_review":True})
    cs=c['capability_summary']
    core=[a['name'] for a in c['demonstrated_abilities'] if not any(('episode' in x) for x in a.get('canonical_refs',[]) ) or n not in CSET]
    cond=[x for x in [clean(cs.get('conditional_abilities'),300)] if x]
    conf='medium' if g=='A' else 'low'
    flags=["PRIMARY_NOT_OPENED"]+extra[n]
    if g=='C': flags.append("CEILING_C_APPLIED")
    if g=='B': flags.append("SECONDARY_ONLY_GRADE_B")
    if conf=='low': flags.append("LOW_CONFIDENCE_INDEPENDENT_REVIEW")
    det[i]={"name":c['name'],"canonical_version":c['canonical_version'],"version_selection_reasoning":c['canonical_version_basis'],
     "core_abilities":core,"conditional_abilities":cond,"excluded_abilities":EXCL.get(n,[]),
     "ability_classes_used":{"C":core,"K":cond,"X":EXCL.get(n,[])},
     "confidence":{"power":conf,**{r:(conf if fit[r]>0 else "n/a (zero)") for r in ROLES}},
     "plausible_alternatives":ALT.get(n,"none recorded"),
     "contradictions_or_outliers":clean(cs.get('limitations'),300) or "none recorded",
     "uncertainty_note":f"Evidence grade {g} (inspected secondary only; primary manga not opened)."+(" Fit zeros are unevidenced zeros (nothing in package) unless limitation text shows absence." ),
     "review_flags":sorted(set(flags))}
G=["Fit was assigned before Power with Power values hidden (fit_reference only; Fit file frozen before power_reference was opened).",
"No rarity, role scores, approval or publication status is assigned in this import file.",
"The corrected research package contains demonstrated capabilities; secondary sources are traceable but primary material was not opened.",
"No Fit value was revised after Pass B."]
root={"format_version":"KA-IMPORT-1.0","batch_type":"evaluation","universe_id":"naruto","batch_id":"naruto-batch-005","evaluation_framework_version":"EVAL-FRAMEWORK-1.0","scoring_version":"SCORE-1.0","canonical_policy_version":"NARUTO-CANON-0.1","batch_status":"draft","global_notes":G,"evaluations":ev}
json.dump(root,open(O+'naruto_batch_005_claude_evaluation.json','w'),indent=2,ensure_ascii=False)
json.dump({"batch_id":"naruto-batch-005","evaluation_details":det},open(O+'naruto_batch_005_evaluation_details.json','w'),indent=2,ensure_ascii=False)
# derived advisory scores (NOT for import)
ds={}
for e in ev:
    ds[e['character_id']]={r:e['fit'][r]*COEF[r]+e['power']*(20-COEF[r]) for r in ROLES}
json.dump({"note":"Advisory derived values using the formula supplied in the owner's prompt. NOT part of the KA-IMPORT file; the attached assignment states SCORE-1.0 derives scores later. No rarity computed: no rarity framework/thresholds were supplied in the package.","formula":"Fit x Coefficient + Power x (20 - Coefficient)","coefficients":COEF,"scores":ds},open(O+'naruto_batch_005_derived_role_scores_advisory.json','w'),indent=2)
# ---- validation
errs=[]
ids=[c['candidate_id'] for c in R]
if [e['character_id'] for e in ev]!=ids: errs.append("order/id mismatch")
for e in ev:
    if not(isinstance(e['power'],int) and 1<=e['power']<=5): errs.append(("power",e['character_id']))
    if list(e['fit'])!=ROLES or any(not(isinstance(v,int) and 0<=v<=5) for v in e['fit'].values()): errs.append(("fit",e['character_id']))
    tg={x['target'] for x in e['evidence']}
    if 'power' not in tg or any(e['fit'][r]>0 and r not in tg for r in ROLES): errs.append(("evidence",e['character_id']))
    if any(k in e for k in('rarity','role_score','ecv_score','matchups','approved')): errs.append("forbidden key")
    for s in ds[e['character_id']].values():
        if not 0<=s<=100: errs.append("score range")
if len(set(ids))!=62: errs.append("dup")
for e in ev:
    for r in ROLES: assert ds[e['character_id']][r]==e['fit'][r]*COEF[r]+e['power']*(20-COEF[r])
print("errors:",errs)
# groups consistency
pw=collections.Counter(e['power'] for e in ev)
rf={r:collections.Counter(e['fit'][r] for e in ev) for r in ROLES}
json.dump({"errors":errs,"power":pw,"fit":{r:dict(v) for r,v in rf.items()}},open('/home/claude/b5/stats.json','w'),default=dict)
print(dict(pw)); 
for r in ROLES: print(r,dict(sorted(rf[r].items())))
nm={c['candidate_id']:c['name'] for c in R}
for r in ROLES:
    top=sorted(ev,key=lambda e:-ds[e['character_id']][r])[:5]
    print(r,[(nm[e['character_id']],ds[e['character_id']][r]) for e in top])
print(collections.Counter(grade(i) for i in ids), sum(1 for d in det.values() if d['confidence']['power']=='medium'))
