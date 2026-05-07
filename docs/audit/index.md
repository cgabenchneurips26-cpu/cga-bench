# CGA-Bench Audit Harness

The audit harness classifies any medical-evaluator function by
projection class (π_term / π_aset / π_nord / π_nctx), reports its
Blind-Spot Rate against the TCC reference, surfaces its plug-in
Bayes-error floor, and produces top-K separating-pair witnesses plus
a domain × violation-type blind-spot grid.

## Two-minute tour

```bash
# 1. Run an audit on a built-in shim
PYTHONPATH=. python scripts/audit/evaluator_audit.py --shim v4_hard --out-dir audit/reports

# 2. Or launch the Gradio demo
pip install -r demo/requirements.txt
PYTHONPATH=. python demo/app.py  # http://localhost:7860

# 3. Verify all 15 shims in one shot
PYTHONPATH=. python scripts/audit/verify_audit_harness.py --fast
```

Each audit produces `report.md` and `report.json` with six sections:

| Step | Content |
|---|---|
| 1 | π-class classification (behavioural test on separating pairs) |
| 2 | Blind-Spot Rate vs TCC reference, false-accept breakdown |
| 3 | Bayes-error floor ε* for the classified π-class |
| 4 | Top-K false-accept witnesses |
| 5 | ρ(d_G) correlation and monotonicity-violation count |
| 6 | Blindspot grid (domain × violation-type) with red/yellow/green cells |

## What is new

Beyond the six Option B shims, recent additions include:

- `active_agent` — TCC-derived diagnostic probe (confirmed omission dominance)
- `pi_nord_witness` — constructive π_nord witness (Bayes floor gap = 164×)
- `ext_medagent_style`, `ext_healthbench_style` — external-benchmark
  style emulators demonstrating the extension pattern
- `ext_medagent_native`, `ext_closedloop_native` — native adapter bridges
  (see [Add your evaluator](add-your-evaluator.md))

## Paper anchors

- **Theorem 3.4** operationalizes classical data-processing for medical
  traces, yielding a plug-in Bayes-error floor (Cor. 3.6) that this
  harness computes on 14,826 episodes.
- **Contribution 4** (§4.4) releases the harness as a reusable artifact:
  CLI + Evaluator ABC + external-benchmark extension + Gradio demo +
  documentation site (this site).

See [Theory](theory.md) for the π-class + Bayes-floor background and
[Worked examples](worked-examples.md) for per-shim audit readouts.
