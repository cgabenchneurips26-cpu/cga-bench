#!/usr/bin/env bash
# Merge mandatory action_effects stubs
set -euo pipefail

AE=cpg_model/action_effects.yaml
STUBS=evidence_pack/fix_actions_v2/mandatory_action_effects.yaml

echo "[1/4] Backup..."
cp $AE ${AE}.bak.$(date +%Y%m%d_%H%M%S)

echo "[2/4] Merge..."
python3 -c "
import yaml
with open('$AE') as f: existing = yaml.safe_load(f) or {}
with open('$STUBS') as f: new = yaml.safe_load(f) or {}
# Remove comment-only keys
new = {k:v for k,v in new.items() if not k.startswith('#')}
merged = {**existing, **new}
print(f'Existing: {len(existing)}, New: {len(new)}, Merged: {len(merged)}')
with open('$AE', 'w') as f: yaml.dump(merged, f, default_flow_style=False, allow_unicode=True)
"

echo "[3/4] Validate..."
python3 -m pytest tests/ -x -q 2>&1 | tail -5

echo "[4/4] Done. Run dry-run to verify:"
echo "  python scripts/full_690_runner.py --dry-run --scenarios 1"
