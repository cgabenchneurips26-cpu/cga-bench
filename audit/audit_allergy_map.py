"""Audit 9: Allergy Drug Map 정확성

penicillin_anaphylaxis가 cephalosporin을 포함하는지 등 핵심 매핑 확인.
"""

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

ALLERGY_MAP_PATH = Path(__file__).parent.parent / "cpg_model" / "allergy_drug_map.yaml"

with open(ALLERGY_MAP_PATH) as f:
    amap = yaml.safe_load(f)

print(f"Total allergy categories: {len(amap)}")
print(f"Total drug mappings: {sum(len(v) for v in amap.values())}")
print()

# Print full map
for allergy, drugs in sorted(amap.items()):
    print(f"  {allergy}: {drugs}")

print()

# Core clinical accuracy checks
checks = [
    ("penicillin_anaphylaxis", "cephalosporin", True, "JACI 2019: ~2% cross-reactivity, higher with anaphylaxis"),
    ("penicillin_anaphylaxis", "ceftriaxone", True, "3rd-gen cephalosporin cross-reactivity"),
    ("penicillin_anaphylaxis", "piperacillin_tazobactam", True, "Beta-lactam: piperacillin IS a penicillin"),
    ("penicillin", "amoxicillin", True, "Same class (aminopenicillin)"),
    ("penicillin", "cephalosporin", False, "Non-anaphylactic penicillin allergy: cephalosporins often safe"),
    ("aspirin", "ibuprofen", False, "Different mechanism -- only cross-reactive in AERD (not standard)"),
    ("sulfa", "furosemide", False, "Sulfonamide antibiotic != sulfonamide non-antibiotic"),
    ("heparin_hit", "enoxaparin", True, "LMWH cross-reactivity in HIT (controversial but standard)"),
    ("heparin_hit", "fondaparinux", True, "Fondaparinux sometimes listed (low risk but cautionary)"),
    ("contrast_dye", "iodinated_contrast", True, "Direct contraindication"),
    ("contrast_dye", "gadolinium", True, "Different mechanism but often co-listed for caution"),
    ("morphine", "codeine", True, "Codeine is metabolized to morphine (CYP2D6)"),
    ("egg", "propofol", True, "Propofol contains egg lecithin (debated but standard)"),
]

print("Clinical accuracy checks:")
pass_count = 0
fail_count = 0
for allergy, drug, should_contain, reason in checks:
    drugs = amap.get(allergy, [])
    contains = drug in drugs
    status = "OK" if contains == should_contain else "WRONG"
    if status == "OK":
        pass_count += 1
    else:
        fail_count += 1
    print(f"  {status}: {allergy} -> {drug}: in_map={contains}, expected={should_contain} ({reason})")

print(f"\n{'=' * 50}")
print(f"Checks passed: {pass_count}/{len(checks)}")
print(f"Checks FAILED: {fail_count}/{len(checks)}")
