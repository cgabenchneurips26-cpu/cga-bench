# CGA-Bench CPG Source Map — 25 Domains
# 확보 방법: A=직접 다운로드(무료PDF/HTML), B=PMC full-text, C=학회 무료 요약, D=페이월(기관접근 필요)
# 
# 전략: web_fetch로 PMC HTML 또는 학회 무료 PDF를 받아 텍스트 추출 → parsed.json 변환
# ============================================================================

# ── 기존 도메인 (기존 parsed.json 있거나, 에피소드 정상 작동) ──────────────

sepsis:
  guideline: "SSC 2021 — Surviving Sepsis Campaign"
  source: "Evans et al. Intensive Care Med 2021;47:1181-1247"
  pmc_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC8486643/"
  method: B  # PMC open access full text
  status: "기존 parsed.json 있음 + PMC로 보강 가능"
  always_empty: false

chest_pain:  # ACS
  guideline: "AHA/ACC 2021 Chest Pain Guideline"
  source: "Gulati et al. Circulation 2021;144:e364-e454"
  pmc_url: null  # AHA journal, 보통 오픈
  direct_url: "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001029"
  method: A  # AHA journals are open access
  status: "기존 parsed.json 있음"
  always_empty: false

stroke:
  guideline: "AHA/ASA 2019 Acute Ischemic Stroke Guidelines"
  source: "Powers et al. Stroke 2019;50:e344-e418"
  direct_url: "https://www.ahajournals.org/doi/10.1161/STR.0000000000000211"
  method: A  # AHA open access
  status: "에피소드 정상"
  always_empty: false

hemorrhagic_stroke:
  guideline: "AHA/ASA 2022 Spontaneous ICH Guidelines"
  source: "Greenberg et al. Stroke 2022;53:e282-e361"
  direct_url: "https://www.ahajournals.org/doi/10.1161/STR.0000000000000407"
  method: A
  status: "에피소드 정상"
  always_empty: false

heart_failure:
  guideline: "AHA/ACC/HFSA 2022 Heart Failure Guideline"
  source: "Heidenreich et al. Circulation 2022;145:e895-e1032"
  direct_url: "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001063"
  method: A
  status: "에피소드 정상"
  always_empty: false

septic_shock:
  guideline: "SSC 2021 (sepsis와 동일 문서)"
  pmc_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC8486643/"
  method: B
  status: "에피소드 정상"
  always_empty: false

hypertensive_emergency:
  guideline: "AHA/ACC 2017 Hypertension Guideline + ESC 2018"
  source: "Whelton et al. JACC 2018;71:e127-e248"
  direct_url: "https://www.ahajournals.org/doi/10.1161/HYP.0000000000000065"
  method: A
  status: "11 always-empty"
  always_empty: true  # partial

# ── 확장 도메인 (빈 에피소드 문제 — RAG 문서 필요) ──────────────────────

aki:
  guideline: "KDIGO 2012 AKI Clinical Practice Guideline"
  source: "KDIGO. Kidney Int Suppl 2012;2:1-138"
  direct_url: "https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-AKI-Guideline-English.pdf"
  method: A  # KDIGO 무료 PDF 직접 다운로드
  status: "61 always-empty — 최우선"
  always_empty: true
  scenarios_affected: 61

caki:  # contrast-induced AKI
  guideline: "KDIGO 2012 AKI (Section 4: CI-AKI) + ACR 2021"
  source: "같은 KDIGO PDF의 Section 4"
  direct_url: "https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-AKI-Guideline-English.pdf"
  alt_source: "ACR Manual on Contrast Media 2021"
  method: A
  status: "37 always-empty"
  always_empty: true
  scenarios_affected: 37

asthma:
  guideline: "GINA 2024 Strategy Report"
  source: "Global Initiative for Asthma 2024"
  direct_url: "https://ginasthma.org/wp-content/uploads/2024/06/GINA-Strategy-Report-2024-tracked-changes-for-archive-WMSA.pdf"
  alt_url: "https://ginasthma.org/wp-content/uploads/2024/12/GINA-Summary-Guide-2024-WEB-WMS.pdf"
  method: A  # GINA 무료 다운로드
  status: "46 always-empty"
  always_empty: true
  scenarios_affected: 46

meningitis:
  guideline: "IDSA 2004 Bacterial Meningitis + ESC/IDSA 2017 CNS Infections"
  source: "Tunkel et al. CID 2004;39:1267-1284"
  pmc_url: null  # 2004는 PMC에 없을 수 있음
  alt_source: "NICE CG102 Meningitis Guidelines (무료)"
  alt_url: "https://www.nice.org.uk/guidance/cg102"
  method: C  # NICE 무료 가이드라인
  status: "31 always-empty"
  always_empty: true
  scenarios_affected: 31

dka:
  guideline: "ADA 2009 DKA Consensus + ADA Standards of Care 2024"
  source: "Kitabchi et al. Diabetes Care 2009;32:1335-1343"
  pmc_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC2699725/"  # DKA 2009
  alt_source: "ADA Standards of Care 2024 (Section 16: Diabetes in Hospital)"
  method: B
  status: "30 always-empty"
  always_empty: true
  scenarios_affected: 30

pe:  # pulmonary embolism
  guideline: "ESC 2019 PE Guidelines"
  source: "Konstantinides et al. Eur Heart J 2020;41:543-603"
  pmc_url: null
  alt_source: "ACCP/ATS PE Guidelines, or ASH 2020 VTE"
  alt_pmc: "https://pmc.ncbi.nlm.nih.gov/articles/PMC7440746/"  # ASH VTE
  direct_url: "https://academic.oup.com/eurheartj/article/41/4/543/5556136"
  method: A  # ESC open access
  status: "24 always-empty"
  always_empty: true
  scenarios_affected: 24

anaphylaxis:
  guideline: "WAO Anaphylaxis Guidance 2020"
  source: "Cardona et al. World Allergy Organ J 2020;13:100472"
  pmc_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC7607509/"
  method: B  # PMC open access
  status: "17 always-empty"
  always_empty: true
  scenarios_affected: 17

status_epilepticus:
  guideline: "AES 2016 SE Treatment + NCS 2012 SE Evaluation"
  source: "Glauser et al. Epilepsy Curr 2016;16:48-61"
  pmc_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC4749120/"
  alt_pdf: "https://neurosciences.ucsd.edu/centers-programs/neurocritical-care/_files/national-guidelines/NCS-status-epilepticus-guideline-2012.pdf"
  method: B  # PMC + 직접 PDF
  status: "16 always-empty"
  always_empty: true
  scenarios_affected: 16

acls:  # cardiac arrest
  guideline: "AHA 2020 ACLS Guidelines (Part 3)"
  source: "Panchal et al. Circulation 2020;142(suppl 2):S366-S468"
  direct_url: "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000916"
  method: A  # AHA open access
  status: "확인 필요"
  always_empty: false  # verify

toxicology:
  guideline: "AACT/EAPCCT Position Papers (여러 독소별)"
  source: "다수 — acetaminophen, salicylate, TCA 등 개별 가이드라인"
  approach: "UpToDate 대신 개별 AACT position papers (PMC 다수)"
  example_pmc:
    - "https://pmc.ncbi.nlm.nih.gov/articles/PMC6326895/"  # NAC for acetaminophen
  method: B  # 개별 PMC papers
  status: "확인 필요"
  note: "여러 독소를 커버하므로 3-5개 핵심 position paper 필요"

pneumonia:
  guideline: "ATS/IDSA 2019 Community-Acquired Pneumonia"
  source: "Metlay et al. Am J Respir Crit Care Med 2019;200:e45-e67"
  direct_url: "https://www.atsjournals.org/doi/10.1164/rccm.201908-1581ST"
  method: A  # ATS open access
  status: "에피소드 확인 필요"
  always_empty: false  # verify

gi_bleed:
  guideline: "ACG 2021 Upper GI Bleeding + BSG 2019"
  source: "Laine et al. Am J Gastroenterol 2021;116:899-917"
  alt_pmc: null  # ACG는 보통 paywall
  alt_source: "NICE NG141 Upper GI Bleeding (무료)"
  alt_url: "https://www.nice.org.uk/guidance/ng141"
  method: C  # NICE 무료
  status: "에피소드 확인 필요"

afib:
  guideline: "AHA/ACC/HRS 2023 AF Guideline"
  source: "Joglar et al. Circulation 2024;149:e167-e295"
  direct_url: "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001193"
  method: A  # AHA open access
  status: "에피소드 확인 필요"
  always_empty: false

# ── Held-out 도메인 (5개) ──────────────────────────────────────────────

burns:
  guideline: "ABA 2018 Burn Guidelines + ISBI 2016"
  source: "ISBI Practice Guidelines. Burns 2016;42:953-1021"
  pmc_url: null  # paywall 가능
  alt_source: "WHO Burns Fact Sheet + UpToDate-equivalent free resources"
  method: D  # 기관접근 필요할 수 있음
  status: "held-out domain"
  note: "emergency burn management는 여러 무료 리소스에서 커버"

transfusion:
  guideline: "AABB 2016 RBC Transfusion Guidelines"
  source: "Carson et al. JAMA 2016;316:2025-2035"
  pmc_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC5207059/"  # 확인 필요
  alt_source: "NICE NG24 Blood Transfusion (무료)"
  alt_url: "https://www.nice.org.uk/guidance/ng24"
  method: B  # PMC if available, else NICE
  status: "held-out domain"

obstetric:
  guideline: "ACOG Practice Bulletins (eclampsia, PPH)"
  source: "여러 ACOG bulletins"
  pmc_url: null  # ACOG는 대부분 paywall
  alt_source: "WHO Recommendations on Maternal Health (무료)"
  alt_url: "https://www.who.int/publications/i/item/9789240073975"
  method: C  # WHO 무료 가이드라인
  status: "held-out domain"
  note: "ACOG 접근 어려우면 WHO + RCOG 무료 가이드라인 사용"

pediatric:
  guideline: "Pediatric sepsis/asthma/seizure 등 개별"
  source: "SSC Peds 2020, GINA Peds, AES Peds 등"
  pmc_url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC7098509/"  # SSC Peds
  method: B
  status: "held-out domain"

psychiatric:
  guideline: "APA 2024 Suicide Risk + Agitation Management"
  source: "APA Practice Guidelines"
  alt_source: "NICE CG178 Self-harm (무료)"
  alt_url: "https://www.nice.org.uk/guidance/ng225"
  method: C  # NICE 무료
  status: "held-out domain"

# ============================================================================
# 실행 계획 요약
# ============================================================================
#
# Phase 1: 즉시 확보 가능 (method A/B) — 18개 도메인
#   web_fetch로 PMC HTML 또는 학회 PDF URL을 직접 받아 텍스트 추출
#   예상 시간: 2-3시간 (자동화 스크립트)
#
# Phase 2: NICE/WHO 무료 가이드라인 (method C) — 4개 도메인
#   meningitis, gi_bleed, obstetric, psychiatric
#   NICE는 HTML로 전문 공개 → web_fetch 가능
#
# Phase 3: 페이월 (method D) — 1개 도메인 (burns)
#   기관 VPN 또는 수동 다운로드 필요
#   대안: WHO Burns guidelines 사용
#
# Phase 4: parsed.json 변환
#   기존 parsed.json 형식에 맞춰 변환
#   sections, recommendations 구조로 파싱
#
# Phase 5: 274개 시나리오 재실행
#   새 RAG corpus로 empty 시나리오만 선택적 재실행
# ============================================================================

# Task: 25개 CPG 원본 PDF 확보 + parsed.json 변환

## 목적

RAG corpus를 원본 CPG PDF 기반으로 재구축한다. LLM 요약본이 아닌 실제 guideline 원문을 사용해야 논문의 신뢰도가 확보된다.

## Step 1: 기존 RAG 코드 파악

```bash
# RAG agent가 parsed.json을 어떻게 로드하는지 확인
cat agents/rag_agent.py | head -100

# _get_source_name() 매핑 확인
grep -n "_get_source_name\|source_name\|cpg_sources" agents/rag_agent.py

# parsed.json을 어떻게 사용하는지 (retrieve 로직)
grep -n "parsed\|json\|load\|recommend\|retrieve\|context" agents/rag_agent.py | head -30

# 기존 parsed.json 하나를 전체 출력 (구조 정확히 파악)
cat cpg_sources/SSC-2021-Sepsis-Hour1-Bundle.parsed.json
```

## Step 2: 25개 CPG의 원본 PDF URL 목록

아래 URL들에서 PDF를 다운로드한다. 일부는 open access, 일부는 저널 접근이 필요할 수 있다.

```python
# scripts/download_cpg_pdfs.py
"""
25개 CPG guideline PDF를 다운로드.
접근 불가한 경우 대안 URL 또는 수동 다운로드 안내.
"""
import urllib.request
import os
from pathlib import Path

PDF_DIR = Path("cpg_sources/pdfs")
PDF_DIR.mkdir(exist_ok=True)

# 25개 CPG PDF URL 목록
# 각 항목: (graph_id, filename, primary_url, alternative_url, citation)
CPG_SOURCES = [
    # === 기존 14개 도메인 (기존 3개도 원본 PDF로 교체) ===
    
    ("ssc_sepsis_hour1_bundle",
     "SSC-2021-Sepsis-Guidelines.pdf",
     "https://sepsis.ch/wp-content/uploads/2024/09/Surviving-Sepsis-Campaign_International-Guidelines-for-Management-of-Sepsis-and-Septic-Shock-2021.pdf",
     "https://link.springer.com/content/pdf/10.1007/s00134-021-06506-y.pdf",
     "Evans L et al. Surviving Sepsis Campaign: International Guidelines 2021. Intensive Care Med. 2021;47:1181-1247"),

    ("aha_chest_pain_evaluation",
     "AHA-2021-Chest-Pain-Guidelines.pdf",
     "https://www.ahajournals.org/doi/pdf/10.1161/CIR.0000000000001029",
     None,
     "Gulati M et al. 2021 AHA/ACC Guideline for Chest Pain. Circulation. 2021;144:e364-e454"),

    ("aha_heart_failure_2022",
     "AHA-2022-Heart-Failure-Guidelines.pdf",
     "https://www.ahajournals.org/doi/pdf/10.1161/CIR.0000000000001063",
     None,
     "Heidenreich PA et al. 2022 AHA/ACC/HFSA Guideline for Management of Heart Failure. Circulation. 2022;145:e895-e1032"),

    ("aha_stroke_2019",
     "AHA-2019-Stroke-Guidelines.pdf",
     "https://www.ahajournals.org/doi/pdf/10.1161/STR.0000000000000211",
     None,
     "Powers WJ et al. 2019 AHA/ASA Guideline for Early Management of Acute Ischemic Stroke. Stroke. 2019;50:e344-e418"),

    ("ada_dka_management",
     "ADA-2024-Standards-of-Care.pdf",
     "https://diabetesjournals.org/care/issue/47/Supplement_1",
     None,
     "ADA Standards of Care in Diabetes 2024. Diabetes Care. 2024;47(Suppl 1)"),

    ("atrial_fibrillation",
     "AHA-2023-AF-Guidelines.pdf",
     "https://www.ahajournals.org/doi/pdf/10.1161/CIR.0000000000001160",
     None,
     "Joglar JA et al. 2023 ACC/AHA/ACCP/HRS Guideline for AF. Circulation. 2024;149:e167-e259"),

    ("cap_pneumonia",
     "ATS-IDSA-2019-CAP-Guidelines.pdf",
     "https://www.atsjournals.org/doi/pdf/10.1164/rccm.201908-1581ST",
     None,
     "Metlay JP et al. ATS/IDSA Guideline for CAP in Adults. Am J Respir Crit Care Med. 2019;200:e45-e67"),

    ("copd_exacerbation",
     "GOLD-2024-COPD-Report.pdf",
     "https://goldcopd.org/2024-gold-report/",
     None,
     "GOLD 2024 Report. Global Strategy for Prevention, Diagnosis and Management of COPD"),

    ("gi_bleeding",
     "ACG-2021-UGIB-Guidelines.pdf",
     "https://journals.lww.com/ajg/fulltext/2021/01000/acg_clinical_guideline__upper_gastrointestinal_and.13.aspx",
     None,
     "Laine L et al. ACG Clinical Guideline: Upper GI and Ulcer Bleeding. Am J Gastroenterol. 2021;116:899-917"),

    ("hypertensive_emergency",
     "AHA-2017-Hypertension-Guidelines.pdf",
     "https://www.ahajournals.org/doi/pdf/10.1161/HYP.0000000000000065",
     None,
     "Whelton PK et al. 2017 ACC/AHA Hypertension Guidelines. Hypertension. 2018;71:e13-e115"),

    ("kdigo_aki_full",
     "KDIGO-2012-AKI-Guidelines.pdf",
     "https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-AKI-Guideline-English.pdf",
     None,
     "KDIGO Clinical Practice Guideline for AKI. Kidney Int Suppl. 2012;2:1-138"),

    ("kdigo_contrast_aki",
     "KDIGO-2012-AKI-Contrast-Section.pdf",
     "https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-AKI-Guideline-English.pdf",
     None,
     "KDIGO AKI Guideline Section 4: Contrast-Induced AKI"),

    ("pulmonary_embolism",
     "ESC-2019-PE-Guidelines.pdf",
     "https://academic.oup.com/eurheartj/article-pdf/41/4/543/31889938/ehz405.pdf",
     None,
     "Konstantinides SV et al. 2019 ESC Guidelines for PE. Eur Heart J. 2020;41:543-603"),

    ("universal_clinical_safety",
     None,  # 특정 CPG 없음, general safety principles
     None,
     None,
     "General clinical safety principles"),

    # === 신규 6개 도메인 ===

    ("anaphylaxis_management",
     "WAO-2020-Anaphylaxis-Guidelines.pdf",
     "https://waojournal.biomedcentral.com/counter/pdf/10.1186/s40413-020-00259-0",
     None,
     "Cardona V et al. WAO Anaphylaxis Guidance 2020. World Allergy Organ J. 2020;13:100472"),

    ("acls_cardiac_arrest",
     "AHA-2020-ACLS-Guidelines.pdf",
     "https://www.ahajournals.org/doi/pdf/10.1161/CIR.0000000000000916",
     None,
     "Panchal AR et al. 2020 AHA Guidelines for CPR and ECC: Adult Advanced Cardiovascular Life Support. Circulation. 2020;142:S366-S468"),

    ("status_epilepticus",
     "AES-2016-Status-Epilepticus.pdf",
     "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1111/epi.13398",
     None,
     "Glauser T et al. Evidence-Based Guideline: Treatment of Convulsive Status Epilepticus. Epilepsy Curr. 2016;16:48-61"),

    ("gina_asthma_exacerbation",
     "GINA-2024-Main-Report.pdf",
     "https://ginasthma.org/wp-content/uploads/2024/05/GINA-2024-Strategy-Report-24_05_22_WMS.pdf",
     None,
     "GINA 2024: Global Strategy for Asthma Management and Prevention"),

    ("idsa_meningitis",
     "IDSA-2004-Meningitis-Guidelines.pdf",
     "https://academic.oup.com/cid/article-pdf/39/9/1267/1225504/39-9-1267.pdf",
     "https://www.idsociety.org/practice-guideline/bacterial-meningitis/",
     "Tunkel AR et al. IDSA Practice Guidelines for Bacterial Meningitis. Clin Infect Dis. 2004;39:1267-1284"),

    ("toxicology_management",
     "AACT-Position-Statements-Collection.pdf",
     None,  # 다수 문서 — 개별 다운로드 필요
     None,
     "AACT/EAPCCT Position Papers (multiple)"),

    # === Held-out 5개 도메인 ===

    ("aba_burn_resuscitation",
     "ABA-2023-Burn-Guidelines.pdf",
     "https://academic.oup.com/jbcr/article-pdf/44/Supplement_1/S1/49477089/irac006.pdf",
     None,
     "Pham TN et al. ABA Practice Guidelines for Burn Resuscitation. J Burn Care Res. 2023;44:S1-S76"),

    ("aabb_transfusion",
     "AABB-2016-RBC-Transfusion-Guidelines.pdf",
     "https://jamanetwork.com/journals/jama/articlepdf/2569055/jsc160021.pdf",
     None,
     "Carson JL et al. Clinical Practice Guidelines from AABB: Red Blood Cell Transfusion Thresholds. JAMA. 2016;316:2025-2035"),

    ("acog_obstetric_hemorrhage",
     "ACOG-2017-PPH-Practice-Bulletin.pdf",
     "https://journals.lww.com/greenjournal/abstract/2017/10000/practice_bulletin_no__183__postpartum_hemorrhage.43.aspx",
     None,
     "ACOG Practice Bulletin No. 183: Postpartum Hemorrhage. Obstet Gynecol. 2017;130:e168-e186"),

    ("pals_pediatric_emergency",
     "AHA-2020-PALS-Guidelines.pdf",
     "https://www.ahajournals.org/doi/pdf/10.1161/CIR.0000000000000901",
     None,
     "Topjian AA et al. 2020 AHA Guidelines for CPR and ECC: Pediatric Advanced Life Support. Circulation. 2020;142:S532-S578"),

    ("apa_agitation_management",
     "BETA-2012-Agitation-Guidelines.pdf",
     "https://westjem.com/wp-content/uploads/2012/11/BETA-Evaluation.pdf",
     "https://escholarship.org/uc/item/0zq2r3b3",
     "Wilson MP et al. The Psychopharmacology of Agitation: Consensus Statement of the AAEP Project BETA Psychopharmacology Workgroup. West J Emerg Med. 2012;13:26-34"),
]

# 다운로드 시도
success = 0
failed = []

for graph_id, filename, primary_url, alt_url, citation in CPG_SOURCES:
    if filename is None:
        print(f"SKIP: {graph_id} — no specific PDF (general principles)")
        continue
    
    dest = PDF_DIR / filename
    if dest.exists():
        print(f"EXISTS: {filename}")
        success += 1
        continue
    
    for url in [primary_url, alt_url]:
        if url is None:
            continue
        try:
            print(f"Downloading: {filename} from {url[:80]}...")
            urllib.request.urlretrieve(url, dest)
            if dest.stat().st_size > 10000:  # 10KB 이상이면 성공
                print(f"  OK: {dest.stat().st_size / 1024:.0f} KB")
                success += 1
                break
            else:
                print(f"  TOO SMALL: {dest.stat().st_size} bytes — may be redirect/error page")
                dest.unlink()
        except Exception as e:
            print(f"  FAIL: {e}")
    else:
        failed.append((graph_id, filename, citation))

print(f"\nDownloaded: {success}")
print(f"Failed: {len(failed)}")
for graph_id, filename, citation in failed:
    print(f"  {graph_id}: {filename}")
    print(f"    Citation: {citation}")
    print(f"    → Manual download needed")
```

**이 스크립트를 실행하라.** 다운로드 실패한 PDF는 수동으로 확보해야 한다.

## Step 3: PDF → parsed.json 변환

다운로드된 PDF를 기존 parsed.json 형식으로 변환한다.

```python
# scripts/parse_cpg_pdfs.py
"""
CPG PDF를 parsed.json 형식으로 변환.

형식:
{
    "recommendations": [
        {"recommendation_id": "...", "text": "...", "strength": "strong/weak", "page": "..."}
    ],
    "tables": [
        {"table_id": "...", "title": "...", "data": [[...]], "page": "..."}
    ],
    "key_sections": {
        "section_name": "section text (max ~2000 chars)"
    }
}
"""
import json
from pathlib import Path

# PDF 텍스트 추출
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

if not HAS_PYPDF2 and not HAS_PYMUPDF:
    print("Install: pip install PyPDF2 pymupdf")
    exit(1)

def extract_text_from_pdf(pdf_path: Path) -> str:
    """PDF에서 전체 텍스트 추출"""
    if HAS_PYMUPDF:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text
    elif HAS_PYPDF2:
        reader = PyPDF2.PdfReader(str(pdf_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

def extract_recommendations(text: str, graph_id: str) -> list:
    """
    텍스트에서 recommendation/강력 권고 추출.
    
    패턴:
    - "We recommend..." / "We suggest..."
    - "Strong recommendation" / "Weak recommendation"
    - "Best practice statement"
    - 번호매김 (1., 2., ...)
    """
    import re
    
    recommendations = []
    
    # 패턴 1: "We recommend/suggest" 문장
    patterns = [
        r'(?:We\s+(?:recommend|suggest)[^.]*\.)',
        r'(?:(?:Strong|Weak)\s+recommendation[^.]*\.)',
        r'(?:Best\s+practice\s+statement[^.]*\.)',
        r'(?:(?:For|In)\s+(?:adults?|patients?|children)\s+with[^.]*(?:we\s+(?:recommend|suggest))[^.]*\.)',
    ]
    
    for i, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            rec_text = match.group().strip()
            if len(rec_text) > 30:  # 너무 짧은 건 제외
                prefix = graph_id.upper().replace("_", "")[:6]
                recommendations.append({
                    "recommendation_id": f"{prefix}_R{len(recommendations)+1}",
                    "text": rec_text[:500],  # 500자 제한
                    "strength": "strong" if "recommend" in rec_text.lower() else "weak" if "suggest" in rec_text.lower() else "best_practice",
                    "page": "auto-extracted"
                })
    
    return recommendations

def extract_key_sections(text: str) -> dict:
    """
    텍스트에서 주요 섹션 추출.
    """
    import re
    
    sections = {}
    
    # 일반적인 CPG 섹션 제목
    section_patterns = [
        "Initial Assessment", "Initial Management", "Initial Resuscitation",
        "Treatment", "Pharmacotherapy", "Drug Therapy",
        "Contraindications", "Do Not", "Avoid",
        "Special Populations", "Special Considerations",
        "Monitoring", "Follow-up",
        "Diagnosis", "Screening",
        "Fluid Management", "Hemodynamic", "Ventilation",
        "Antibiotic", "Antimicrobial",
        "Emergency", "Urgent", "Critical",
    ]
    
    for section_name in section_patterns:
        # 섹션 제목 이후 텍스트 추출
        pattern = rf'(?:{section_name})\s*\n([\s\S]{{100,2000}}?)(?=\n[A-Z][a-z]{{3,}}|\Z)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            sections[section_name.lower().replace(" ", "_")] = match.group(1).strip()[:2000]
    
    return sections

def parse_single_pdf(pdf_path: Path, graph_id: str) -> dict:
    """단일 PDF를 parsed.json으로 변환"""
    text = extract_text_from_pdf(pdf_path)
    
    recommendations = extract_recommendations(text, graph_id)
    key_sections = extract_key_sections(text)
    
    parsed = {
        "source_pdf": pdf_path.name,
        "graph_id": graph_id,
        "total_pages": text.count("\n\n"),  # 대략적 페이지 수
        "recommendations": recommendations,
        "tables": [],  # PDF 테이블 추출은 복잡 — 우선 빈 배열
        "key_sections": key_sections,
        "full_text_length": len(text),
    }
    
    return parsed

# 메인 실행
PDF_DIR = Path("cpg_sources/pdfs")
OUTPUT_DIR = Path("cpg_sources")

# graph_id → PDF 매핑
GRAPH_PDF_MAP = {
    "ssc_sepsis_hour1_bundle": "SSC-2021-Sepsis-Guidelines.pdf",
    "aha_chest_pain_evaluation": "AHA-2021-Chest-Pain-Guidelines.pdf",
    "aha_heart_failure_2022": "AHA-2022-Heart-Failure-Guidelines.pdf",
    "aha_stroke_2019": "AHA-2019-Stroke-Guidelines.pdf",
    "ada_dka_management": "ADA-2024-Standards-of-Care.pdf",
    "atrial_fibrillation": "AHA-2023-AF-Guidelines.pdf",
    "cap_pneumonia": "ATS-IDSA-2019-CAP-Guidelines.pdf",
    "copd_exacerbation": "GOLD-2024-COPD-Report.pdf",
    "gi_bleeding": "ACG-2021-UGIB-Guidelines.pdf",
    "hypertensive_emergency": "AHA-2017-Hypertension-Guidelines.pdf",
    "kdigo_aki_full": "KDIGO-2012-AKI-Guidelines.pdf",
    "kdigo_contrast_aki": "KDIGO-2012-AKI-Contrast-Section.pdf",
    "pulmonary_embolism": "ESC-2019-PE-Guidelines.pdf",
    "anaphylaxis_management": "WAO-2020-Anaphylaxis-Guidelines.pdf",
    "acls_cardiac_arrest": "AHA-2020-ACLS-Guidelines.pdf",
    "status_epilepticus": "AES-2016-Status-Epilepticus.pdf",
    "gina_asthma_exacerbation": "GINA-2024-Main-Report.pdf",
    "idsa_meningitis": "IDSA-2004-Meningitis-Guidelines.pdf",
    "aba_burn_resuscitation": "ABA-2023-Burn-Guidelines.pdf",
    "aabb_transfusion": "AABB-2016-RBC-Transfusion-Guidelines.pdf",
    "acog_obstetric_hemorrhage": "ACOG-2017-PPH-Practice-Bulletin.pdf",
    "pals_pediatric_emergency": "AHA-2020-PALS-Guidelines.pdf",
    "apa_agitation_management": "BETA-2012-Agitation-Guidelines.pdf",
}

results = []

for graph_id, pdf_name in GRAPH_PDF_MAP.items():
    pdf_path = PDF_DIR / pdf_name
    
    if not pdf_path.exists():
        print(f"SKIP: {graph_id} — PDF not found: {pdf_name}")
        results.append({"graph_id": graph_id, "status": "MISSING_PDF"})
        continue
    
    print(f"\nParsing: {graph_id} ({pdf_name})...")
    
    try:
        parsed = parse_single_pdf(pdf_path, graph_id)
        
        # 저장 — 기존 naming convention에 맞게
        output_name = pdf_name.replace(".pdf", ".parsed.json")
        output_path = OUTPUT_DIR / output_name
        
        with open(output_path, "w") as f:
            json.dump(parsed, f, indent=2)
        
        print(f"  Recommendations: {len(parsed['recommendations'])}")
        print(f"  Key sections: {len(parsed['key_sections'])}")
        print(f"  Full text: {parsed['full_text_length']:,} chars")
        print(f"  Saved: {output_path}")
        
        results.append({
            "graph_id": graph_id,
            "status": "OK",
            "recommendations": len(parsed["recommendations"]),
            "sections": len(parsed["key_sections"]),
            "text_length": parsed["full_text_length"],
        })
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append({"graph_id": graph_id, "status": f"ERROR: {e}"})

# 결과 요약
print("\n" + "=" * 60)
print("PARSING SUMMARY")
print("=" * 60)
ok = [r for r in results if r["status"] == "OK"]
print(f"Successfully parsed: {len(ok)}/{len(GRAPH_PDF_MAP)}")
for r in ok:
    print(f"  {r['graph_id']}: {r['recommendations']} recs, {r['sections']} sections")

failed = [r for r in results if r["status"] != "OK"]
if failed:
    print(f"\nFailed: {len(failed)}")
    for r in failed:
        print(f"  {r['graph_id']}: {r['status']}")
```

## Step 4: _get_source_name() 매핑 확장

```python
# agents/rag_agent.py의 _get_source_name() 수정
# 기존 3개 매핑을 25개로 확장

SOURCE_NAME_MAP = {
    # 기존
    "Sepsis": "ssc_sepsis",
    "Chest-Pain": "aha_chest_pain",
    "KDIGO": "kdigo_aki",
    
    # 신규 확장 — 파일명 키워드 → graph domain
    "Heart-Failure": "aha_heart_failure",
    "Stroke": "aha_stroke",
    "DKA": "ada_dka",
    "Standards-of-Care": "ada_dka",
    "AF-Guidelines": "atrial_fibrillation",
    "CAP": "cap_pneumonia",
    "GOLD": "copd",
    "COPD": "copd",
    "UGIB": "gi_bleeding",
    "Gastrointestinal": "gi_bleeding",
    "Hypertension": "hypertensive_emergency",
    "AKI": "kdigo_aki",
    "Contrast": "kdigo_contrast",
    "PE-Guidelines": "pulmonary_embolism",
    "Pulmonary-Embolism": "pulmonary_embolism",
    "Anaphylaxis": "anaphylaxis",
    "ACLS": "acls",
    "Status-Epilepticus": "status_epilepticus",
    "Epilepsy": "status_epilepticus",
    "GINA": "gina_asthma",
    "Asthma": "gina_asthma",
    "Meningitis": "idsa_meningitis",
    "Toxicology": "toxicology",
    "AACT": "toxicology",
    "Burn": "aba_burn",
    "ABA": "aba_burn",
    "Transfusion": "aabb_transfusion",
    "AABB": "aabb_transfusion",
    "RBC": "aabb_transfusion",
    "PPH": "acog_obstetric",
    "Obstetric": "acog_obstetric",
    "Hemorrhage": "acog_obstetric",  # 주의: GI bleed과 구분 필요
    "PALS": "pals_pediatric",
    "Pediatric": "pals_pediatric",
    "Agitation": "apa_agitation",
    "BETA": "apa_agitation",
    "Psychopharmacology": "apa_agitation",
}
```

하지만 **실제 구현은 rag_agent.py를 읽은 후 기존 로직에 맞게 수정해야 한다.** _get_source_name()이 파일명 기반인지, 시나리오 기반인지에 따라 매핑 방식이 달라진다.

## Step 5: 파싱 품질 검증

```python
# scripts/verify_parsed_cpgs.py
"""
파싱된 parsed.json의 품질 검증:
1. 각 파일에 recommendations가 있는가
2. 각 recommendation이 임상적으로 의미있는 텍스트인가
3. key_sections가 도메인과 관련있는가
"""
import json
from pathlib import Path

CPG_DIR = Path("cpg_sources")

for json_file in sorted(CPG_DIR.glob("*.parsed.json")):
    with open(json_file) as f:
        data = json.load(f)
    
    recs = data.get("recommendations", [])
    sections = data.get("key_sections", {})
    
    print(f"\n{json_file.name}:")
    print(f"  Recommendations: {len(recs)}")
    
    if recs:
        # 첫 3개 recommendation 출력
        for r in recs[:3]:
            print(f"    [{r.get('strength', '?')}] {r.get('text', '')[:100]}...")
    else:
        print(f"  *** WARNING: No recommendations extracted! ***")
    
    print(f"  Key sections: {list(sections.keys())}")
    
    # 최소 기준
    if len(recs) < 3:
        print(f"  *** LOW QUALITY: only {len(recs)} recommendations ***")
```

## Step 6: 274개 Empty 시나리오 재실행

parsed.json이 모두 준비된 후:

```bash
# 1. Empty 시나리오 목록 확인
wc -l configs/empty_scenario_list.txt

# 2. 재실행 (5개 모델)
bash scripts/experiments/rerun_empty.sh

# 3. 결과 병합
python scripts/merge_rerun_results.py

# 4. Empty rate 재확인
python scripts/midrun_check.py
```

## Completion Criteria

- [ ] 24개 PDF 다운로드 완료 (universal_clinical_safety 제외)
- [ ] 24개 parsed.json 생성
- [ ] 각 parsed.json에 recommendations ≥ 5개
- [ ] _get_source_name() 25개 도메인 매핑
- [ ] RAG agent가 새 문서를 로드하는지 확인
- [ ] 274개 empty 시나리오 재실행
- [ ] 재실행 후 empty rate < 10%