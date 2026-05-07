# Extending CGA-Bench

This guide explains how to add new clinical domains, CPG graphs, scenarios, and agent rules to CGA-Bench. It documents the YAML schemas derived from the existing 14 CPG graphs and 16 scenario configuration files.

---

## Table of Contents

1. [YAML CPG Graph Schema](#1-yaml-cpg-graph-schema)
2. [Scenario Configuration Schema](#2-scenario-configuration-schema)
3. [Step-by-Step: Adding a New Domain](#3-step-by-step-adding-a-new-domain)
4. [Validation Checklist](#4-validation-checklist)
5. [Testing New Domains](#5-testing-new-domains)
6. [Adding a Custom Evaluator](#6-adding-a-custom-evaluator)
7. [Common Pitfalls](#7-common-pitfalls)

---

## 1. YAML CPG Graph Schema

CPG graph files live in `cpg_model/graphs/` and define the clinical guideline logic that the CPG Engine evaluates against. Each file represents one clinical guideline (e.g., SSC Sepsis Hour-1 Bundle, AHA Chest Pain Evaluation).

### Top-Level Fields

```yaml
# REQUIRED fields
graph_id: "string"           # Unique identifier, referenced by scenario configs
guideline_name: "string"     # Human-readable guideline name
version: "string"            # Guideline version (e.g., "2021.1")
entry_node: "string"         # ID of the first node in the graph

# REQUIRED metadata block
metadata:
  source: "string"           # Short guideline source name
  doi: "string"              # Digital Object Identifier
  source_url: "string"       # URL to the guideline publication
  journal: "string"          # Journal name
  citation: "string"         # Full citation string
  recommendation_system: "string"  # "GRADE" or "ACC/AHA Class/LOE"
  description: "string"      # Brief description of what this guideline covers

  # OPTIONAL metadata (guideline-specific)
  pmcid: "string"            # PubMed Central ID
  doi_jacc: "string"         # Secondary DOI (e.g., JACC mirror)
  bundle_window_minutes: int # Time window for bundle completion
  key_evidence: "string"     # Key evidence summary
  key_recommendation: "string"  # Primary recommendation text
  key_quote: "string"        # Direct quote from the guideline

# REQUIRED node definitions
nodes:
  node_id_1:
    # ... (see Node Schema below)
  node_id_2:
    # ...

# OPTIONAL (used by universal_clinical_safety.yaml only)
action_categories:           # Categorized action lists for modular evaluation
  category_name:
    - "action_id_1"
    - "action_id_2"

modular_rules:               # Domain-independent evaluation rules
  rule_name:
    check_type: "any_of|sequence_required"
    actions: [...]
    penalty_if_missing: float
```

### Node Schema

Each node in the `nodes` dict represents a clinical decision point, action plan, or assessment step.

```yaml
node_id:
  # --- REQUIRED fields ---
  node_id: "string"          # Must match the dict key
  node_type: "string"        # One of: "decision", "plan", "action", "enquiry"
  name: "string"             # Human-readable node name
  description: "string"      # What this node represents clinically

  mandatory_actions:          # Actions that MUST be performed at this node
    - "action_id_1"
    - "action_id_2"

  allowed_actions:            # ALL permissible actions (superset of mandatory)
    - "action_id_1"
    - "action_id_2"
    - "action_id_3"           # Optional actions listed here too

  source_guideline: "string"  # Guideline citation (e.g., "SSC 2021", "AHA/ACC 2021")
  source_section: "string"    # Section reference (e.g., "Section 2.3.2", "Initial Resuscitation")

  # --- OPTIONAL fields ---
  precondition: "string|null"  # Python-style condition for node activation
                                # e.g., "state.working_diagnosis == 'septic_shock'"

  forbidden_actions:           # Contraindicated actions (default: [])
    - "forbidden_action_id"

  deadlines:                   # Time constraints in minutes (default: {})
    action_id_1: 10            # Must complete within 10 minutes
    action_id_2: 60

  required_prior_actions:      # Prerequisites (default: {})
    action_id_2:               # Before action_id_2 can be performed...
      - "action_id_1"          # ...action_id_1 must be completed first

  recommendation_class: "string"  # "I", "IIa", "IIb", or "III"
  evidence_level: "string"       # "A", "B", "B-NR", "C", "C-LD", "C-EO"

  source_page: "string"       # Page reference in the guideline
  source_figure: "string"     # Figure reference (e.g., "Figure 4")
  source_quote: "string"      # Direct quote supporting this node
  source_loe: "string"        # Level of Evidence notation

  next_nodes:                  # Unconditional successors (default: [])
    - "next_node_id"

  conditional_next:            # Conditional transitions (default: {})
    "state.working_diagnosis == 'septic_shock'": "septic_shock_bundle"
    "state.working_diagnosis == 'sepsis'": "sepsis_bundle"
```

### Node Type Descriptions

| `node_type` | Purpose | Example |
|-------------|---------|---------|
| `decision`  | Branch point based on patient state | "Sepsis Recognition" -- routes to sepsis vs septic_shock |
| `plan`      | Multi-action treatment plan | "Hour-1 Bundle" -- list of mandatory bundle actions |
| `action`    | Single clinical action | "Administer tPA" -- one specific intervention |
| `enquiry`   | Assessment or data-gathering step | "Initial Chest Pain Assessment" -- gather ECG, vitals |

### Action ID Conventions

Action IDs follow a consistent naming pattern:

| Pattern | Description | Examples |
|---------|-------------|----------|
| `assess_*` | Clinical assessment | `assess_vital_signs`, `assess_nihss` |
| `order_lab_*` | Laboratory order | `order_lab_lactate`, `order_lab_troponin` |
| `order_imaging_*` | Imaging order | `order_imaging_chest_xray`, `order_imaging_ct_head` |
| `give_*` | Medication administration | `give_aspirin`, `give_broad_spectrum_antibiotics` |
| `start_*` | Initiate therapy/infusion | `start_vasopressor_norepinephrine`, `start_insulin_infusion` |
| `obtain_*` | Obtain specific data | `obtain_12_lead_ecg`, `obtain_chest_pain_history` |
| `activate_*` | Activate a clinical pathway | `activate_cath_lab`, `activate_stroke_code` |
| `consult_*` | Specialist consultation | `consult_nephrology`, `consult_gi_for_endoscopy` |
| `place_*` | Device/line placement | `place_central_line`, `place_arterial_line` |
| `reassess_*` | Re-evaluation | `reassess_perfusion`, `remeasure_lactate_if_elevated` |

### Example: Minimal Valid Graph

```yaml
graph_id: "example_minimal"
guideline_name: "Example Minimal Guideline"
version: "1.0"

metadata:
  source: "Example Source 2024"
  doi: "10.xxxx/example"
  description: "Minimal example for documentation"

entry_node: "initial"

nodes:
  initial:
    node_id: "initial"
    node_type: "enquiry"
    name: "Initial Assessment"
    description: "Perform initial patient assessment"
    precondition: null
    mandatory_actions:
      - "assess_vital_signs"
    allowed_actions:
      - "assess_vital_signs"
      - "order_lab_cbc"
    forbidden_actions: []
    deadlines:
      assess_vital_signs: 10
    required_prior_actions: {}
    recommendation_class: "I"
    evidence_level: "B"
    source_guideline: "Example Source 2024"
    source_section: "Section 1"
    source_page: "p1"
    source_quote: "All patients should have vital signs assessed within 10 minutes."
    next_nodes: []
    conditional_next: {}
```

---

## 2. Scenario Configuration Schema

Scenario files live in `configs/scenarios/` and define clinical patient encounters used to test agents. Each file contains multiple scenarios for a single domain.

### Top-Level Structure

```yaml
scenarios:
  scenario_id_1:
    # ... (see Scenario Schema below)
  scenario_id_2:
    # ...
```

### Scenario Schema

```yaml
scenario_id:
  # --- REQUIRED fields ---
  scenario_id: "string"         # Must match the dict key
  description: "string"         # Clinical scenario description
  guideline_graph: "string"     # References graph_id or domain_registry key
                                 # e.g., "ssc_sepsis_hour1", "aha_chest_pain"

  patient:                       # Patient presentation
    age: int                     # Patient age in years
    sex: "M|F"                   # Biological sex
    weight_kg: float             # Body weight in kg
    chief_complaint: "string"    # Presenting complaint
    working_diagnosis: "string"  # Initial diagnosis
                                 # Used for conditional_next routing in CPG graph

    vitals:                      # Initial vital signs
      heart_rate: int            # bpm
      blood_pressure_systolic: int   # mmHg
      blood_pressure_diastolic: int  # mmHg
      respiratory_rate: int      # breaths/min
      temperature: float         # Celsius
      oxygen_saturation: int     # SpO2 percentage
      map_mmhg: int              # Mean Arterial Pressure

    allergies: [list]            # Drug allergies (e.g., ["penicillin"])
    comorbidities: [list]        # Pre-existing conditions
                                 # (e.g., ["type_1_diabetes", "hypertension"])
    contraindications: [list]    # Specific contraindications

  expected_actions:              # Actions the agent SHOULD perform
    - "action_id_1"              # Must be non-empty
    - "action_id_2"

  max_duration_minutes: int      # Simulation time limit (e.g., 90, 120)
  passing_compliance_threshold: float  # Minimum CGA score to pass (e.g., 0.8)

  # --- OPTIONAL fields ---
  ground_truth:                  # Lab/imaging results returned by environment
    lab_lactate: float
    lab_troponin: float
    ecg_result: "string"
    imaging_chest_xray: "string"
    # ... any key-value pairs appropriate to the domain

  forbidden_actions:             # Patient-specific forbidden actions
    - "action_id"                # Augments graph-level forbidden_actions

  trap_scenario: bool            # Whether this is an adversarial trap (default: false)
  trap_description: "string"     # Description of the clinical trap
```

### Trap Scenarios

Trap scenarios test whether agents avoid common clinical pitfalls. They are identified by `trap_scenario: true` and typically include `forbidden_actions` that represent the trap.

Example -- RV Infarct Nitrate Trap:

```yaml
stemi_inferior_rv_trap:
  scenario_id: "stemi_inferior_rv_trap"
  description: "Inferior STEMI with RV involvement - nitrate contraindicated"
  guideline_graph: "aha_chest_pain"
  trap_scenario: true
  trap_description: "RV infarct - nitrates cause severe hypotension"

  patient:
    # ... vitals showing bradycardia and borderline hypotension
    working_diagnosis: "inferior_stemi"

  expected_actions:
    - "obtain_12_lead_ecg"
    - "obtain_right_sided_ecg_v4r"   # Key: must check for RV involvement
    - "start_iv_fluid_bolus"          # RV infarct needs preload, not nitrates

  forbidden_actions:
    - "give_nitroglycerin"   # THE TRAP: nitrates contraindicated in RV infarct
    - "give_nitrates"
    - "give_morphine"        # Relative contraindication in hypotensive patient
```

---

## 3. Step-by-Step: Adding a New Domain

This walkthrough demonstrates adding **Community-Acquired Pneumonia (CAP)** as a new domain. The same process applies to any clinical guideline.

### Step 1: Create the CPG Graph YAML

Create `cpg_model/graphs/cap_pneumonia.yaml`:

```yaml
# Community-Acquired Pneumonia (CAP) Guidelines
# Source: IDSA/ATS 2019 CAP Guidelines
# DOI: 10.1164/rccm.201908-1581ST

graph_id: "cap_pneumonia"
guideline_name: "IDSA/ATS Community-Acquired Pneumonia 2019"
version: "2019.1"

metadata:
  source: "IDSA/ATS CAP Guidelines 2019"
  doi: "10.1164/rccm.201908-1581ST"
  source_url: "https://doi.org/10.1164/rccm.201908-1581ST"
  journal: "American Journal of Respiratory and Critical Care Medicine"
  citation: "Am J Respir Crit Care Med. 2019;200(7):e45-e67"
  recommendation_system: "GRADE"
  description: "Management of community-acquired pneumonia in adults"

entry_node: "initial_assessment"

nodes:
  initial_assessment:
    node_id: "initial_assessment"
    node_type: "decision"
    name: "CAP Initial Assessment"
    description: "Assess pneumonia severity using CURB-65 or PSI"
    precondition: null
    mandatory_actions:
      - "assess_vital_signs"
      - "assess_respiratory_status"
      - "order_imaging_chest_xray"
      - "order_lab_cbc"
    allowed_actions:
      - "assess_vital_signs"
      - "assess_respiratory_status"
      - "order_imaging_chest_xray"
      - "order_lab_cbc"
      - "order_lab_bmp"
      - "order_lab_procalcitonin"
      - "assess_curb65"
    forbidden_actions: []
    deadlines:
      order_imaging_chest_xray: 60
    required_prior_actions: {}
    recommendation_class: "I"
    evidence_level: "A"
    source_guideline: "IDSA/ATS 2019"
    source_section: "Diagnosis"
    source_page: "e45"
    source_quote: "Chest radiography should be obtained to confirm diagnosis"
    next_nodes: []
    conditional_next:
      "state.working_diagnosis == 'severe_cap'": "severe_cap_icu"
      "state.working_diagnosis == 'inpatient_cap'": "inpatient_cap"

  inpatient_cap:
    node_id: "inpatient_cap"
    node_type: "plan"
    name: "Inpatient CAP Management"
    description: "Non-ICU inpatient pneumonia treatment"
    precondition: "state.working_diagnosis == 'inpatient_cap'"
    mandatory_actions:
      - "order_lab_blood_culture"
      - "give_beta_lactam_plus_macrolide"
    allowed_actions:
      - "order_lab_blood_culture"
      - "order_lab_procalcitonin"
      - "give_beta_lactam_plus_macrolide"
      - "give_respiratory_fluoroquinolone"
      - "give_iv_fluids"
      - "order_lab_sputum_culture"
    forbidden_actions: []
    deadlines:
      give_beta_lactam_plus_macrolide: 240
    required_prior_actions:
      give_beta_lactam_plus_macrolide:
        - "order_lab_blood_culture"
    recommendation_class: "I"
    evidence_level: "A"
    source_guideline: "IDSA/ATS 2019"
    source_section: "Treatment"
    source_page: "e52"
    source_quote: "Beta-lactam plus macrolide or respiratory fluoroquinolone for inpatient non-ICU CAP"
    next_nodes: []
    conditional_next: {}

  severe_cap_icu:
    node_id: "severe_cap_icu"
    node_type: "plan"
    name: "Severe CAP ICU Management"
    description: "ICU-level management for severe pneumonia"
    precondition: "state.working_diagnosis == 'severe_cap'"
    mandatory_actions:
      - "order_lab_blood_culture"
      - "order_lab_sputum_culture"
      - "give_beta_lactam_plus_macrolide"
      - "assess_need_for_vasopressors"
    allowed_actions:
      - "order_lab_blood_culture"
      - "order_lab_sputum_culture"
      - "order_lab_procalcitonin"
      - "give_beta_lactam_plus_macrolide"
      - "give_respiratory_fluoroquinolone"
      - "give_iv_fluids"
      - "assess_need_for_vasopressors"
      - "start_vasopressor_norepinephrine"
      - "assess_intubation_need"
      - "perform_intubation"
    forbidden_actions: []
    deadlines:
      give_beta_lactam_plus_macrolide: 60
    required_prior_actions:
      give_beta_lactam_plus_macrolide:
        - "order_lab_blood_culture"
    recommendation_class: "I"
    evidence_level: "A"
    source_guideline: "IDSA/ATS 2019"
    source_section: "Severe CAP"
    source_page: "e56"
    source_quote: "Severe CAP: beta-lactam plus macrolide; obtain cultures before antibiotics"
    next_nodes: []
    conditional_next: {}
```

### Step 2: Create Scenario Configs

Create `configs/scenarios/cap_pneumonia_scenarios.yaml`:

```yaml
scenarios:
  cap_inpatient_basic:
    scenario_id: "cap_inpatient_basic"
    description: "Standard inpatient community-acquired pneumonia"
    guideline_graph: "cap_pneumonia"

    patient:
      age: 68
      sex: "M"
      weight_kg: 75
      chief_complaint: "productive cough, fever, dyspnea for 3 days"
      working_diagnosis: "inpatient_cap"

      vitals:
        heart_rate: 95
        blood_pressure_systolic: 130
        blood_pressure_diastolic: 78
        respiratory_rate: 24
        temperature: 38.6
        oxygen_saturation: 92
        map_mmhg: 95

      allergies: []
      comorbidities: []
      contraindications: []

    ground_truth:
      imaging_chest_xray: "right_lower_lobe_consolidation"
      lab_wbc: 15200
      lab_procalcitonin: 2.8
      lab_blood_culture: "streptococcus_pneumoniae"

    expected_actions:
      - "assess_vital_signs"
      - "order_imaging_chest_xray"
      - "order_lab_cbc"
      - "order_lab_blood_culture"
      - "give_beta_lactam_plus_macrolide"

    max_duration_minutes: 120
    passing_compliance_threshold: 0.8

  cap_severe_icu:
    scenario_id: "cap_severe_icu"
    description: "Severe CAP requiring ICU admission with vasopressor support"
    guideline_graph: "cap_pneumonia"
    trap_scenario: false

    patient:
      age: 72
      sex: "F"
      weight_kg: 60
      chief_complaint: "high fever, severe dyspnea, confusion"
      working_diagnosis: "severe_cap"

      vitals:
        heart_rate: 115
        blood_pressure_systolic: 82
        blood_pressure_diastolic: 48
        respiratory_rate: 32
        temperature: 39.4
        oxygen_saturation: 86
        map_mmhg: 59

      allergies: []
      comorbidities:
        - "copd"
        - "diabetes_type_2"
      contraindications: []

    ground_truth:
      imaging_chest_xray: "bilateral_infiltrates"
      lab_wbc: 22000
      lab_procalcitonin: 8.5
      lab_lactate: 3.8
      lab_blood_culture: "legionella_pneumophila"

    expected_actions:
      - "assess_vital_signs"
      - "order_imaging_chest_xray"
      - "order_lab_blood_culture"
      - "order_lab_sputum_culture"
      - "give_beta_lactam_plus_macrolide"
      - "assess_need_for_vasopressors"

    max_duration_minutes: 120
    passing_compliance_threshold: 0.8
```

### Step 3: Register the Domain

Add an entry to `configs/domain_registry.yaml`:

```yaml
# Add under the 'domains:' key
  pneumonia:
    guideline_id: "cpg_model/graphs/cap_pneumonia.yaml"
    en_keywords:
      - "pneumonia"
      - "cap"
      - "community acquired pneumonia"
      - "hospital acquired pneumonia"
      - "lung infection"
    cn_keywords:
      - "肺炎"
      - "社区获得性肺炎"
      - "肺部感染"
    action_keywords_cn:
      "胸片": "order_imaging_chest_xray"
      "痰培养": "order_lab_sputum_culture"
      "降钙素原": "order_lab_procalcitonin"
```

The `cpg_model/domain_registry.py` module loads this YAML automatically. No code changes needed for domain detection.

### Step 4: Add Action Mappings to the Normalizer

Edit `assessor_core/action_normalizer.py` and add domain-specific direct mappings. The normalizer has three layers applied in order:

1. **Domain-specific mappings** (highest priority) -- keyed by `cpg_id`
2. **Direct mappings** -- global exact-match dictionary
3. **Pattern rules** -- regex-based transformations
4. **Fuzzy matching** -- Jaccard similarity with 0.7 threshold (last resort)

Add to the `DIRECT_MAPPINGS` dict (or `domain_specific_mappings` if the mapping is CAP-only):

```python
# In the DIRECT_MAPPINGS section of ActionNormalizer
# Pneumonia / CAP
"chest_xray": "order_imaging_chest_xray",
"sputum_culture": "order_lab_sputum_culture",
"blood_culture": "order_lab_blood_culture",
"antibiotics_cap": "give_beta_lactam_plus_macrolide",
"fluoroquinolone": "give_respiratory_fluoroquinolone",
"curb65": "assess_curb65",
"curb_65_score": "assess_curb65",
"procalcitonin": "order_lab_procalcitonin",
```

### Step 5: Create Agent Rules (Optional)

If you want Oracle agent support for the new domain, create `agent_rules/cap_pneumonia_rules.py`:

```python
"""
CAP Decision Table: IDSA/ATS 2019 guideline-based independent rules.

Source: IDSA/ATS CAP Guidelines 2019
DOI: 10.1164/rccm.201908-1581ST

This implementation is COMPLETELY INDEPENDENT from cpg_engine.
Same guideline text, different code path.
"""

from cga_bench.agent_rules.decision_table import (
    RuleBasedDecisionTable,
    ClinicalRuleSet,
    DecisionTableEntry,
    ClinicalCondition,
    ActionRecommendation,
    ConditionOperator,
)


class CAPDecisionTable(RuleBasedDecisionTable):
    """IDSA/ATS 2019 CAP Decision Table (Oracle agent)."""

    def _load_rulesets(self):
        # Define rulesets for severity tiers
        # ... (follow the pattern in dka_rules.py or sepsis_rules.py)
        pass

    def _determine_scenario_type(self, context) -> str:
        # Route to "severe_cap" vs "inpatient_cap" based on vitals
        # ... (check MAP, SpO2, mental status)
        pass
```

**Critical**: The Oracle agent uses `agent_rules/` exclusively and must NEVER import from `cpg_engine/`. This is the Scoring-Agent Separation principle.

### Step 6: Write Tests

Create test files following the existing patterns:

```
tests/
  test_engine/test_cap_pneumonia.py     # CPG engine evaluation
  test_golden/cases/cap/               # Golden pair A/B snapshots
```

Minimal engine test example:

```python
"""Tests for CAP pneumonia CPG graph evaluation."""
import pytest
from pathlib import Path
import yaml

GRAPH_PATH = Path(__file__).parent.parent.parent / "cpg_model" / "graphs" / "cap_pneumonia.yaml"


def test_graph_loads():
    """Graph file loads without error."""
    data = yaml.safe_load(GRAPH_PATH.read_text())
    assert data["graph_id"] == "cap_pneumonia"
    assert "initial_assessment" in data["nodes"]


def test_mandatory_subset_of_allowed():
    """All mandatory actions must also appear in allowed actions."""
    data = yaml.safe_load(GRAPH_PATH.read_text())
    for node_id, node in data["nodes"].items():
        mandatory = set(node.get("mandatory_actions", []))
        allowed = set(node.get("allowed_actions", []))
        assert mandatory <= allowed, (
            f"Node {node_id}: mandatory actions {mandatory - allowed} "
            f"not in allowed_actions"
        )


def test_no_forbidden_in_allowed():
    """Forbidden and allowed actions must not overlap."""
    data = yaml.safe_load(GRAPH_PATH.read_text())
    for node_id, node in data["nodes"].items():
        forbidden = set(node.get("forbidden_actions", []))
        allowed = set(node.get("allowed_actions", []))
        overlap = forbidden & allowed
        assert not overlap, (
            f"Node {node_id}: {overlap} in both forbidden and allowed"
        )
```

### Step 7: Run Validation

```bash
# Validate the new graph schema
PYTHONPATH=. python scripts/ci/validate_cpg_schema.py

# Run source traceability audit
PYTHONPATH=. python scripts/ci/audit_sources.py

# Run all tests
PYTHONPATH=. pytest tests/ -v

# Run only the new domain tests
PYTHONPATH=. pytest tests/test_engine/test_cap_pneumonia.py -v
```

---

## 4. Validation Checklist

Use this checklist before submitting a new domain:

### CPG Graph (`cpg_model/graphs/*.yaml`)

- [ ] `graph_id` is unique across all graph files
- [ ] `guideline_name`, `version`, and `metadata` block are present
- [ ] `entry_node` references a node that exists in `nodes`
- [ ] Every node has: `node_id`, `node_type`, `name`, `description`
- [ ] Every node has: `mandatory_actions`, `allowed_actions`
- [ ] `mandatory_actions` is a subset of `allowed_actions`
- [ ] `forbidden_actions` does NOT overlap with `allowed_actions`
- [ ] `deadlines` only reference actions in `mandatory_actions` or `allowed_actions`
- [ ] `required_prior_actions` reference valid action IDs
- [ ] All `next_nodes` and `conditional_next` targets exist in `nodes`
- [ ] `source_guideline` and `source_section` are filled for every node
- [ ] `node_id` value matches its dict key
- [ ] `node_type` is one of: `decision`, `plan`, `action`, `enquiry`

### Scenario Config (`configs/scenarios/*.yaml`)

- [ ] `scenario_id` value matches its dict key
- [ ] `guideline_graph` references a valid `graph_id` or domain registry key
- [ ] `patient` block includes: `age`, `sex`, `weight_kg`, `chief_complaint`, `working_diagnosis`, `vitals`
- [ ] `vitals` includes at minimum: `heart_rate`, `blood_pressure_systolic`, `blood_pressure_diastolic`, `temperature`, `oxygen_saturation`
- [ ] `expected_actions` is non-empty
- [ ] `forbidden_actions` (if present) do NOT overlap with `expected_actions`
- [ ] `max_duration_minutes` is a positive integer
- [ ] `passing_compliance_threshold` is between 0.0 and 1.0
- [ ] Trap scenarios have `trap_scenario: true` and `trap_description`

### Domain Registry (`configs/domain_registry.yaml`)

- [ ] Domain key is lowercase with underscores
- [ ] `guideline_id` points to the correct YAML file path
- [ ] `en_keywords` includes the most common English terms
- [ ] At least 3 keywords per language

### Action Normalizer (`assessor_core/action_normalizer.py`)

- [ ] All new action IDs have direct mappings for common agent-generated variants
- [ ] No collisions with existing mappings

### Agent Rules (Optional)

- [ ] Rule file does NOT import from `cpg_engine/`
- [ ] Rule file does NOT import from `assessor_core/`
- [ ] `get_independence_verification()` returns `uses_cpg_engine: False`

---

## 5. Testing New Domains

### Automated Schema Validation

```bash
# Validate all CPG graphs and scenario configs
PYTHONPATH=. python scripts/ci/validate_cpg_schema.py
```

### Golden Pair Testing

Golden pairs provide A/B contrasting scenarios: scenario A follows the guideline correctly, scenario B commits a specific violation. Create golden pairs in `tests/test_golden/cases/<domain>/<scenario_name>/`:

```
tests/test_golden/cases/cap/
  antibiotic_delay/
    expected_A.json   # Correct: antibiotics within 4 hours
    expected_B.json   # Violation: antibiotics delayed beyond deadline
```

### Full Test Suite

```bash
# Run all tests including the new domain
PYTHONPATH=. pytest tests/ -v --tb=short

# Run only engine tests
PYTHONPATH=. pytest tests/test_engine/ -v

# Run only golden pair tests
PYTHONPATH=. pytest tests/test_golden/ -v
```

---

## 6. Adding a Custom Evaluator

The audit harness (`audit/`) accepts **any** episode-level evaluator via the `Evaluator` ABC. This section shows how to add one in under 15 minutes.

### Minimal Template (5 lines)

```python
from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import load_w8_episodes

class MyEvaluator(Evaluator):
    meta = EvaluatorMeta(name="MyEval", family="custom", source="my_source")

    def verdict(self, ep: dict) -> bool:
        data = load_w8_episodes().get(ep["episode_id"])
        if data is None:
            return False
        return data.get("n_viols", 0) == 0  # Your logic here
```

### Contract

| Requirement | Details |
|-------------|---------|
| **Inherit** | `audit.evaluator_base.Evaluator` |
| **Class attribute** | `meta: EvaluatorMeta` with `name`, `family`, `source` |
| **Method** | `verdict(self, ep: dict[str, Any]) -> bool` |
| **Deterministic** | No network calls, no LLM calls at audit time |
| **Side-effect free** | No file writes, no state mutation |
| **Optional** | `observed_features() -> frozenset[str]` — hints for pi-class |

### Available Episode Fields

`load_w8_episodes()` returns `dict[episode_id, dict]` with these fields per episode:

| Field | Type | Description |
|-------|------|-------------|
| `episode_id` | `str` | Unique episode identifier |
| `scenario_id` | `str` | Scenario that was run |
| `model` | `str` | Model name |
| `run_index` | `int` | Run number (0, 1, 2) |
| `n_viols` | `int` | Total violation count |
| `viol_types` | `list[str]` | e.g. `["COMMISSION", "TIMING"]` |
| `c2_score` | `float` | Mandatory completion score |
| `action_coverage` | `float` | Fraction of expected actions performed |
| `mab_f1` | `float` | Mandatory action F1 |
| `dxem` / `ac_proxy` / ... | `bool` | Pre-computed verdicts from built-in evaluators |

### Running the Audit

```bash
# Run the 6-step audit on your evaluator
make audit-evaluator-one EVAL=path.to.module:MyEvaluator

# Example with a shim in audit/shims/
make audit-evaluator-one EVAL=audit.shims.violation_count_shim:ViolationCountEvaluator
```

### Expected Output

The audit produces `audit/reports/<name>/report.json` with 6 steps:

1. **pi-class** — Projection class from separating pairs (`term`, `aset`, `nord`, `nctx`)
2. **BSR** — Blind-Spot Rate vs V4Hard reference (0.0 to 1.0)
3. **Bayes floor** — Minimum achievable error for this pi-class
4. **Witnesses** — Top-K false-accept episodes with domain distribution
5. **Repair distance** — Spearman rho between evaluator and violation count
6. **Blindspot grid** — Domain x violation-type disagreement heatmap

### Registration (Optional)

To include your evaluator in `make audit-evaluator` (batch run), add it to `audit/shims/__init__.py`:

```python
from audit.shims.my_shim import MyEvaluator

SHIM_REGISTRY: dict[str, type] = {
    # ... existing entries ...
    "my_eval": MyEvaluator,
}
```

### Example: ViolationCountEvaluator

See `audit/shims/violation_count_shim.py` — a live-computation evaluator that weights COMMISSION/TIMING violations at 2x and passes if the weighted score is below 3.0. Its audit results: pi-class=`nctx`, BSR=0.64, rho(d_G)=-0.81.

---

## 7. Common Pitfalls

### 7.1: `guideline_graph` Key Mismatch

The scenario's `guideline_graph` field must match either:
- The `graph_id` field in the CPG graph YAML, OR
- A domain key in `configs/domain_registry.yaml`

It does NOT match the filename. For example, `ssc_sepsis_hour1` (not `ssc_sepsis_hour1.yaml`, not `ssc_sepsis_hour1_bundle`).

### 7.2: Mandatory Not in Allowed

Every action in `mandatory_actions` MUST also appear in `allowed_actions`. The CPG Engine treats `allowed_actions` as the complete set of permissible actions. If a mandatory action is missing from `allowed_actions`, it will be flagged as a deviation when performed.

### 7.3: `unmapped:` Prefix

Do NOT return action IDs with an `unmapped:` prefix from the normalizer. This breaks downstream ViolationExtractor and CPGEngine set comparisons. Track unmapped actions internally via `_unmapped_actions`.

### 7.4: Scoring-Agent Separation

Agent code (in `agent_runner/`, `agent_rules/`) must NEVER import from scoring code (`cpg_engine/`, `assessor_core/`). This is enforced by `tests/test_isolation/` and `scripts/ci/leakage_scan.py`.

### 7.5: Oracle Independence

The Oracle agent uses `agent_rules/` decision tables that are independently implemented from CPG graph definitions. They reference the same guideline text but use separate code, separate action IDs, and separate condition logic. Do not copy node IDs or structures from the CPG graph into agent rules.
