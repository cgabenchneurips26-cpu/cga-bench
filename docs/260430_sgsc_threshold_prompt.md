You are working on Track β of CGA-Bench Path D Day 1: SGSC pipeline configuration + normalizer wire-in + overnight 25-guideline atom proposal kickoff.

CONTEXT:
- We are preparing the SGSC pipeline to generate the v7 corpus tonight (overnight) so that v7 episode rerun can start tomorrow afternoon.
- Track α (a separate session) is fixing the ActionNormalizer (N1/N2 circular alias, N3-N5 residual, B3 forbidden symmetric). You will need their normalizer fixes for β-4 onwards. β-1 through β-3 are independent and can run before α completes.
- A SYNCHRONIZATION POINT exists: β-4 must NOT begin until anonymous-user confirms Track α has reached "α-4 COMPLETE" (normalizer + violations fixes verified, all tests pass).
- Total Track β budget: ~3h active work + overnight automated run.

REPO LAYOUT (locate first if uncertain):
- Entailment checker: sgsc/verification/entailment_checker.py
- SGSC pipeline: sgsc/pipeline.py
- SGSC config: probably PipelineConfig in sgsc/pipeline.py or sgsc/config.py
- Atom proposer: sgsc/proposer/ (likely)
- Graph builder: sgsc/builder/ (likely)
- 25-guideline runner: scripts/sgsc/run_full_25.py (already exists from P1 phase)
- Existing tests: tests/test_sgsc/

After each task, STOP, print "β-N COMPLETE" + 3-line summary. Wait for confirmation.

═══════════════════════════════════════════════════════════════
TASK β-1: Add stemming to entailment checker (target ~0.5h)
═══════════════════════════════════════════════════════════════

OBJECTIVE: Resolve the use_balanced_crystalloids contradiction by adding plural/singular stemming to keyword matching.

ROOT CAUSE: Atom canonical_id "use_balanced_crystalloids" (plural) vs source quote "crystalloid" (singular). Substring match `"crystalloids" in quote_lower` fails. Stemming closes this gap.

STEPS:
1. Open sgsc/verification/entailment_checker.py
2. Locate _check_action_entailment around lines 100-108. Confirm the current logic:
     matches = sum(1 for p in meaningful if p in quote_lower)
3. Add a helper function above _check_action_entailment:

def _stem_match(keyword: str, text: str) -> bool:
    """Match keyword in text with simple plural/singular stemming."""
    if keyword in text:
        return True
    # singular form: crystalloids -> crystalloid
    if keyword.endswith("s") and keyword[:-1] in text:
        return True
    if keyword.endswith("es") and keyword[:-2] in text:
        return True
    # plural form: crystalloid -> crystalloids
    if (keyword + "s") in text:
        return True
    return False

4. Replace the matches line:
     matches = sum(1 for p in meaningful if _stem_match(p, quote_lower))
5. Search the file for any other place that does `keyword in text`-style matching for atom validation. If similar logic exists in _check_guard_entailment or other field checks, apply the same stemming there. Document each site you patched.
6. Add 3 unit tests in tests/test_sgsc/test_entailment_checker.py:
   - test_stem_match_plural_to_singular: canonical_id="use_balanced_crystalloids", quote contains "balanced crystalloid solution" → ENTAILED with ratio 1.0
   - test_stem_match_singular_to_plural: canonical_id="administer_crystalloid", quote contains "crystalloids should be" → ENTAILED
   - test_stem_match_no_false_positive: canonical_id="give_aspirin" should NOT match a quote containing only "asprins" (verify the plural form requires the original keyword to be a real prefix — be careful here, this test will check that random pluralization doesn't introduce false positives)
7. Run: PYTHONPATH=. pytest tests/test_sgsc/test_entailment_checker.py -v
   ALL must pass including the 3 new ones.

DELIVERABLES:
- Modified sgsc/verification/entailment_checker.py
- Added tests in tests/test_sgsc/test_entailment_checker.py
- Brief note: which sites in the entailment checker were patched

STOP. Print "β-1 COMPLETE". Wait.

═══════════════════════════════════════════════════════════════
TASK β-2: Forward grounding_threshold from PipelineConfig (target ~0.25h)
═══════════════════════════════════════════════════════════════

OBJECTIVE: Fix the dead-code bug where pipeline.py:168 calls check_atoms_entailment() without forwarding the threshold from PipelineConfig.

STEPS:
1. Open sgsc/pipeline.py. Find the call to check_atoms_entailment (around line 168).
2. Current:
     entailment_reports = check_atoms_entailment(atoms, mode=config.entailment_mode)
3. Patch:
     entailment_reports = check_atoms_entailment(
         atoms,
         mode=config.entailment_mode,
         action_threshold=config.grounding_threshold,
         guard_threshold=config.grounding_threshold,
     )
4. Verify check_atoms_entailment signature in sgsc/verification/entailment_checker.py accepts action_threshold and guard_threshold kwargs. If not, add them with appropriate forwarding.
5. Add a unit test in tests/test_sgsc/test_pipeline.py (or wherever pipeline tests live):
   - test_threshold_forwarding: monkeypatch check_atoms_entailment, verify it receives the threshold from PipelineConfig.

DELIVERABLES:
- Modified sgsc/pipeline.py
- Possibly modified sgsc/verification/entailment_checker.py signature
- New test test_threshold_forwarding

STOP. Print "β-2 COMPLETE". Wait.

═══════════════════════════════════════════════════════════════
TASK β-3: Raise default thresholds to 0.6 (target ~0.5h)
═══════════════════════════════════════════════════════════════

OBJECTIVE: Update the default action and guard thresholds from 0.5 to 0.6.

STEPS:
1. In sgsc/verification/entailment_checker.py around lines 83-84, change:
     _DEFAULT_ACTION_THRESHOLD = 0.6   # was 0.5
     _DEFAULT_GUARD_THRESHOLD = 0.6    # was 0.5
2. In sgsc/pipeline.py PipelineConfig (or wherever the dataclass lives), change:
     grounding_threshold: float = 0.6  # was 0.5
3. Search for any test that hardcodes 0.5 as the default threshold expectation and update them to 0.6. Run:
   grep -r "0.5" tests/test_sgsc/ | grep -i threshold
4. Re-run the existing 9-atom Pilot-14 entailment if there's an existing test fixture for it, OR create a small ad-hoc verification script: scripts/sgsc/verify_threshold_change.py
   - Loads sgsc_output/ssc_sepsis_hour1_bundle/atoms_smoke.json (the only existing atoms file)
   - Runs check_atoms_entailment with the new defaults + your β-1 stemming fix
   - Reports: ENTAILED count, NOT_ENTAILED count, contradiction count
5. Print expected vs actual:
   - Before β-1 + β-3: 1 contradiction (use_balanced_crystalloids), 6 fuzzy-only, 3 rejected, 0 strict
   - After β-1 + β-3: 0 contradictions, X ENTAILED, Y rejected, ? strict
   - The contradiction count MUST drop to 0. If not, β-1 stemming is incomplete; STOP and report.
6. Run: PYTHONPATH=. pytest tests/test_sgsc/ -v
   ALL must pass.

DELIVERABLES:
- Modified sgsc/verification/entailment_checker.py and sgsc/pipeline.py
- Updated tests
- scripts/sgsc/verify_threshold_change.py
- Console: before/after Pilot-14 9-atom counts

STOP. Print "β-3 COMPLETE — STEMMING + THRESHOLD VERIFIED ON PILOT-14". Wait for anonymous-user confirmation BEFORE proceeding to β-4 (synchronization point with Track α).

═══════════════════════════════════════════════════════════════
SYNCHRONIZATION POINT: WAIT FOR TRACK α "α-4 COMPLETE"
═══════════════════════════════════════════════════════════════

DO NOT START β-4 until anonymous-user confirms Track α has reached α-4 COMPLETE.
Why: β-4 wires the ActionNormalizer into the SGSC pipeline. The normalizer must include the N1/N2/N3-N5 fixes from α before being wired in, otherwise v7 corpus will inherit those bugs.

While waiting, you may:
- Idle (preferred)
- Or do a paper text task if anonymous-user assigns one

═══════════════════════════════════════════════════════════════
TASK β-4: Wire ActionNormalizer into SGSC post-LLM step (target ~1h)
═══════════════════════════════════════════════════════════════

PRECONDITION: Track α has confirmed α-4 COMPLETE.

OBJECTIVE: After the SGSC atom proposer (LLM) returns atom JSON, deterministically canonicalize all action IDs through the (now-fixed) ActionNormalizer before saving the atom file. This is the safety net that prevents v7 from inheriting N1/N2/N3-N5 vocabulary bugs.

STEPS:
1. Locate the atom proposer flow in sgsc/proposer/. Identify the function that takes LLM JSON output and returns the validated/saved atom list. (Likely something like propose_atoms or run_atom_proposer.)
2. Identify the schema of an atom: it should have a canonical_id field and possibly other action-bearing fields (e.g., required_prior, forbidden_actions inside constraints, etc.).
3. Add a post-process step that:
   - Imports ActionNormalizer
   - For each atom, normalizes all action-bearing fields:
       atom["canonical_id"] = normalizer.normalize(atom["canonical_id"])
       if atom["constraint"].get("required_prior"):
           atom["constraint"]["required_prior"] = normalizer.normalize(atom["constraint"]["required_prior"])
       # Any other action-bearing fields — search the schema thoroughly
   - Logs any normalization that changed the value (so we can audit later)
4. CRITICAL: This step MUST be deterministic and run AFTER the LLM call but BEFORE entailment checking. Otherwise entailment will run on raw LLM output and reject atoms that would have passed in canonical form. Position the patch correctly.
5. Add a unit test:
   - Mock the LLM to return an atom with canonical_id="assess_urine_output"
   - Run propose_atoms
   - Assert that the saved atom has canonical_id=="monitor_urine_output" (post-normalizer)
6. Run: PYTHONPATH=. pytest tests/test_sgsc/ -v

DELIVERABLES:
- Modified sgsc/proposer/<file>
- New unit test
- Brief note on which atom fields are now post-normalized

STOP. Print "β-4 COMPLETE". Wait.

═══════════════════════════════════════════════════════════════
TASK β-5: Normalize forbidden_actions in graph builder (target ~0.5h)
═══════════════════════════════════════════════════════════════

OBJECTIVE: Ensure SGSC's graph builder, when assembling forbidden_actions lists from atoms, normalizes them (B3 fix applied to the SGSC corpus generation, not just scoring).

STEPS:
1. Locate sgsc/builder/graph_builder.py (or equivalent). Find the code that aggregates forbidden_actions from atoms into graph nodes.
2. Apply ActionNormalizer.normalize to every forbidden_action before insertion into the graph YAML.
3. Same for any scenario-level forbidden_actions if SGSC also generates scenarios.
4. Add unit test: input an atom with raw forbidden form, verify graph YAML output contains canonical form.
5. Run sgsc tests.

DELIVERABLES:
- Modified graph builder
- New unit test

STOP. Print "β-5 COMPLETE". Wait.

═══════════════════════════════════════════════════════════════
TASK β-6: Integration test of β-1 through β-5 (target ~0.5h)
═══════════════════════════════════════════════════════════════

OBJECTIVE: End-to-end smoke test that the SGSC pipeline produces canonical, source-grounded atoms with proper threshold enforcement.

STEPS:
1. Run a single-guideline SGSC pipeline (the existing ssc_sepsis_hour1_bundle is the cleanest test target) with the new code:
   PYTHONPATH=. python scripts/sgsc/run_pilot_14.py --guideline ssc_sepsis_hour1_bundle --threshold 0.6 (or whatever the existing CLI is — adapt as needed)
2. Compare against the existing sgsc_output/ssc_sepsis_hour1_bundle/atoms_smoke.json:
   - Confirm 0 contradictions (was 1)
   - Confirm canonical_ids are normalized (no assess_* if monitor_* is canonical)
   - Confirm forbidden_actions in any output graph are normalized
3. Run full SGSC test suite: PYTHONPATH=. pytest tests/test_sgsc/ -v
4. Run ruff: ruff check sgsc/

DELIVERABLES:
- Console comparison report
- All tests passing
- ruff clean

STOP. Print "β-6 COMPLETE — SGSC PIPELINE READY FOR 25-GUIDELINE OVERNIGHT RUN". Wait for confirmation BEFORE β-7.

═══════════════════════════════════════════════════════════════
TASK β-7: Kickoff SGSC-3 25-guideline overnight run (target 0.25h kickoff + 8-10h automated)
═══════════════════════════════════════════════════════════════

PRECONDITION: β-6 confirmed clean.

OBJECTIVE: Start the overnight SGSC-3 run that produces atoms for all 25 guidelines using the now-fixed pipeline.

STEPS:
1. Locate scripts/sgsc/run_full_25.py (from P1 phase). Read its CLI.
2. Verify the registry: configs/sgsc/full_25_registry.json. Confirm 25 entries, paths exist (the dry-run mode).
3. Choose endpoint. Check what's available:
   - LLM endpoint anonymous-user normally uses (the same that produced ssc_sepsis_hour1_bundle atoms)
   - If unsure, ask anonymous-user.
4. Pre-flight: PYTHONPATH=. python scripts/sgsc/run_full_25.py --dry-run
   Confirm 25/25 validated, 0 errors.
5. Real kickoff (long-running, run in background or nohup):
   nohup PYTHONPATH=. python scripts/sgsc/run_full_25.py \
     --endpoint <ENDPOINT> \
     --threshold 0.6 \
     --output-dir sgsc_output/v7_atoms_overnight/ \
     > reports/path_d_day1/sgsc_3_overnight.log 2>&1 &
   echo $! > reports/path_d_day1/sgsc_3_pid.txt

6. After kickoff, verify the process is alive: ps -p $(cat reports/path_d_day1/sgsc_3_pid.txt)
7. Check the log after 5 minutes — confirm atoms are being proposed (look for guideline-completion log lines)
8. Print:
   - PID
   - Log path
   - Output dir
   - Expected completion time: now + 10h
   - How to check progress: tail -f reports/path_d_day1/sgsc_3_overnight.log

DELIVERABLES:
- Running background process
- Log file growing
- anonymous-user can monitor and walk away

Print "β-7 COMPLETE — SGSC-3 RUNNING. CHECK BACK AT [TIME+10h]."

═══════════════════════════════════════════════════════════════
EXECUTION ORDER: β-1 → β-2 → β-3 → [WAIT FOR α-4] → β-4 → β-5 → β-6 → β-7
═══════════════════════════════════════════════════════════════

Begin with β-1. First confirm understanding by listing all 7 tasks and noting the synchronization point. Then start β-1.