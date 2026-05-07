# EXP-4: Proxy Fidelity — Main Text Summary

## Main Text Paragraph (for Section 5 / Verdict Analysis)

Controlled-trace fidelity audit (5 synthetic DKA episodes) confirms that
proxy scorers are design-blind to the most clinically dangerous violation
types. Trace T4 performs all 10 mandatory actions but delays potassium
correction by 30 minutes past the 60-minute deadline — both AC-Proxy
(coverage = 1.0) and MAB-Proxy (F1 = 1.0) certify it as safe, while
CGA-Bench correctly flags the timing violation (C4, severity = major).
Trace T5 performs all mandatory actions *and* administers insulin before
potassium correction — a Class I contraindication in DKA hypokalemia that
risks fatal cardiac arrhythmia — yet both proxies again certify it as safe,
while CGA-Bench detects the commission violation (C3, severity = major).
Overall, 3 of 5 traces receive false-pass certification from both proxies
(Table~\ref{tab:proxy_fidelity_main}), confirming that process blindness
is design-inherent and not an artifact of proxy implementation or
threshold choice.

## Appendix Reference

The full 5-trace evaluation matrix with per-metric breakdown (coverage,
F1, precision, recall, C2, HardViol types) is available in
Table~\ref{tab:proxy_fidelity} (Appendix).

## Key Numbers for Paper

- AC-Proxy false pass rate: **3/5 (60%)**
- MAB-Proxy false pass rate: **3/5 (60%)**
- CGA-Bench false pass rate: **0/5 (0%)**
- Key traces: T4 (timing blindness) and T5 (commission blindness)
- Both T4 and T5 achieve coverage = 1.0, F1 = 1.0, C2 = 1.0
  but HardViol = True (timing / commission with severity = major)
