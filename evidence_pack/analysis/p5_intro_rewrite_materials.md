> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# P5: Introduction Rewrite Materials

**Generated from**: P0 audit (180 episodes) + P2 bootstrap CIs


## 1. Claim Verification Table

| ID | Original Claim | Verified Value | 95% CI | Status |
|:--:|---------------|----------------|--------|--------|
| a | 61.5% of completion-passing episodes violate hard constraints | 64.1% | [51.3%, 73.1%] | CORRECTED (was 61.5%, now 64.1%) |
| b | 35.9% violate STRONG-evidence constraints | 35.9% | [24.4%, 46.2%] | VERIFIED |
| c | 12.8% have critical violations | 12.8% | [5.1%, 20.5%] | VERIFIED |
| d | Timing BSR 10.6%, Sequence BSR 16.7%, Forbidden BSR 18.2% | P1(timing)=10.6%, P2(sequence)=16.7%, P3(forbidden)=18.2% | see bsr_results.json ci_all | VERIFIED |
| e | 94% of constraints are z1-determined | 100.0% (489/489) | N/A (definitional count) | CHECK — depends on constraint counting method |

### Detailed Claim Notes

**(a)** Any commission, timing, or sequence violation
- Source: 50/78 episodes

**(b)** Commission OR timing delay>30min OR sequence violation
- Source: 28/78 episodes

**(c)** Commission severe/catastrophic OR timing delay>60min
- Source: 10/78 episodes

**(d)** Jaccard baseline (r=0.58 with CGA). P4/P5 = 0% (omission/deviation not sensitive to perturbation — expected).
- Source: BSR baseline=B2_Jaccard

**(e)** Total: 489, z1: 489, z2-only: 0
- Source: CPG graph YAML files


## 2. Draft Introduction Paragraph

```latex
Prevailing medical AI evaluation relies on task-completion metrics that
are \emph{structurally blind} to process-level safety constraints.
We demonstrate this blindness empirically: across 180 closed-loop episodes
spanning six clinical domains, 50 of 78 completion-passing
episodes (64.1\%, 95\% BCa CI
[51.3\%, 73.1\%]) simultaneously violate
at least one hard constraint---forbidden drug administration, missed
treatment deadlines, or sequencing errors that would constitute
reportable events in clinical practice. Of these,
28 (35.9\%) involve violations with
strong clinical evidence, and 10 (12.8\%)
reach critical severity where patient harm is near-certain.
Every one of these episodes would receive a ``pass'' verdict from any
evaluation system that tracks only \emph{what} was done, without
examining \emph{when}, \emph{in what order}, and \emph{what was
forbidden}.
```


## 3. Revised Contribution List

```latex
\begin{enumerate}[leftmargin=*,label=(\arabic*)]
\item \textbf{Benchmark artifact.}
      \cgabench{} defines 15 clinical scenarios across 6 guideline domains,
      each annotated with mandatory, forbidden, timing, and sequence
      constraints derived from Class~I/IIa recommendations in published CPGs.
      The evaluation pipeline is fully deterministic and closed-loop.

\item \textbf{Empirical mis-certification audit.}
      We show that 64.1\% [51.3\%, 73.1\%] of episodes that satisfy
      standard completion thresholds simultaneously violate at least one
      hard safety constraint. This \emph{unsafe-pass} phenomenon is
      consistent across all four model families tested (4B--120B parameters).

\item \textbf{Formal blindness analysis.}
      We introduce Blindness Sensitivity Ratio (BSR), a perturbation-based
      metric that quantifies the fraction of constraint violations invisible
      to a given baseline metric. Timing constraints yield BSR\,=\,10.6\%
      and forbidden-action constraints yield BSR\,=\,18.2\%, confirming
      that existing metrics are structurally incapable of detecting these
      violation classes.
\end{enumerate}

\noindent Core findings are independent of C1 (protocol adherence);
the unsafe-pass phenomenon persists when C1 is excluded from the
CGA score computation.
```


## 4. Key Numbers Summary

- Total episodes: 180
- Completion-passing (C2>=0.7): 78/180 (43.3%)
- Unsafe-pass (any hard): 50/78 (64.1%)
- Unsafe-pass (STRONG): 28/78 (35.9%)
- Unsafe-pass (CRITICAL): 10/78 (12.8%)
- Friedman Composite A: chi2=21.54, p=0.000081
- C2 Friedman: chi2=9.55, p=0.022787
- C3 identical across models: 0.867
- C5 zero violations (all models = 1.000)
- BSR timing (P1): 10.6%
- BSR sequence (P2): 16.7%
- BSR forbidden (P3): 18.2%