# Competing Medical AI Benchmarks — Structural Analysis

> **Last updated**: 2026-04-01
> **Purpose**: Reference for positioning CGA-Bench against competing benchmarks in the NeurIPS 2026 paper.

---

## 1. Benchmark Comparison Matrix

| Benchmark | Venue | Episodes | Domains | Evaluation Type | Code/Data | Key Differentiator |
|-----------|-------|----------|---------|-----------------|-----------|-------------------|
| **CGA-Bench** (ours) | NeurIPS 2026 ED | 180 (internal) + 17,784 (cross) | 6 clinical | Closed-loop CPG compliance | GitHub + PhysioNet | 5-construct violation taxonomy, temporal scoring |
| **AgentClinic** | NeurIPS 2024 | 321 | 9 specialties | Multimodal diagnosis | GitHub + HuggingFace | Patient-doctor dialogue simulation, 24 biases |
| **HealthBench** | arXiv 2025 | 5,000 conversations | General health | Rubric-based multi-judge | GitHub + HuggingFace | 48,562 rubric criteria, 262 physician validators |
| **BetterBench** | NeurIPS 2024 Spotlight | Meta-benchmark | Cross-domain | Lifecycle-based evaluation | GitHub | 46 criteria across 4 lifecycle stages |
| **MedAgentBench** | NEJM AI 2025 | 300 tasks | 10 categories | EHR task completion | GitHub + Stanford STARR | FHIR-compliant, multi-step EHR workflows |
| **MedChain** | NeurIPS 2025 Poster | 12,163 cases | 19 specialties | Multi-step clinical workflow | GitHub | 5 clinical stages, chain-of-reasoning |

---

## 2. Detailed Benchmark Profiles

### 2.1 AgentClinic (NeurIPS 2024)

**Paper**: "AgentClinic: A Multimodal Agent Benchmark to Evaluate AI in Simulated Clinical Environments"

**Structure**:
- **Scale**: 321 patient cases across 9 medical specialties, 7 languages
- **Design**: Patient-doctor dialogue simulation with multimodal inputs (text + images)
- **Bias Framework**: 24 cognitive/implicit biases modeled
- **Data**: MIMIC-IV based (shared foundation with CGA-Bench)
- **Evaluation**: Diagnostic accuracy + treatment appropriateness

**Paper Organization** (estimated ~20 pages with appendix):
1. Introduction + motivation (clinical simulation gap)
2. Related work (medical QA vs. clinical simulation)
3. AgentClinic framework design
4. Bias modeling methodology
5. Experiments (multiple LLMs across specialties)
6. Results + analysis (per-specialty, per-bias breakdowns)
7. Limitations + ethical considerations

**CGA-Bench Differentiation**:
- AgentClinic focuses on **diagnosis** accuracy; CGA-Bench on **treatment protocol adherence**
- AgentClinic has broader specialty coverage but shallower per-domain evaluation
- CGA-Bench's 5-construct violation taxonomy provides more granular safety insights
- Cross-benchmark comparison: 12.5% discordant rate (AgentClinic vs CGA scoring)

---

### 2.2 HealthBench (OpenAI, 2025)

**Paper**: "HealthBench: A Benchmark for Evaluating Health-Related Language Model Responses"

**Structure**:
- **Scale**: 5,000 multi-turn conversations, 48,562 rubric criteria
- **Validation**: 262 physicians across multiple specialties
- **License**: MIT (fully open)
- **Platform**: HuggingFace datasets
- **Evaluation**: Rubric-based scoring with physician-validated criteria

**Paper Organization**:
1. Introduction (health AI evaluation gap)
2. Dataset construction methodology
   - Conversation generation
   - Rubric criteria development
   - Physician validation process
3. Benchmark design
   - Scoring methodology
   - Inter-rater reliability
4. Experiments
   - Multiple LLM evaluation
   - Human baseline comparison
5. Analysis
   - Per-topic breakdowns
   - Error taxonomy
6. Discussion + limitations

**Key Numbers**:
- 7 health topics
- 3-level severity scoring
- Inter-rater kappa > 0.7
- Available on HuggingFace under MIT license

**CGA-Bench Differentiation**:
- HealthBench evaluates general health **information quality**; CGA-Bench evaluates **clinical action safety**
- HealthBench uses rubric-based scoring; CGA-Bench uses CPG-graph-based violation detection
- Cross-benchmark: 19.4% discordant rate — HealthBench tends to over-classify safety issues (84% over-classification in 50-sample audit)
- CGA-Bench has temporal dimension (timing violations, deadlines) that HealthBench lacks

---

### 2.3 BetterBench (NeurIPS 2024 Spotlight)

**Paper**: "BetterBench: Assessing AI Benchmarks, Uncovering Issues, and Establishing Best Practices"

**Structure**:
- **Type**: Meta-benchmark (evaluates benchmarks, not models)
- **Framework**: 46 criteria across 4 lifecycle stages
- **Coverage**: 25 existing benchmarks evaluated
- **Contribution**: Best practices for benchmark design

**Lifecycle Stages**:
1. **Design** — Problem formulation, scope, metrics selection
2. **Construction** — Data collection, annotation, quality control
3. **Deployment** — Accessibility, documentation, maintenance
4. **Evaluation** — Statistical rigor, reproducibility, fairness

**CGA-Bench Relevance**:
- BetterBench is not a competitor but a **quality standard** we should reference
- Use BetterBench criteria as a self-audit checklist
- Citing BetterBench strengthens our methodology claims
- Key criteria CGA-Bench should highlight:
  - Construct validity (5 sub-constructs with Friedman tests)
  - Statistical rigor (Holm-Bonferroni, LOSO, bootstrap CI)
  - Reproducibility (fixed seeds, public code)
  - Discriminant validity (BSR = 5.1%)

---

### 2.4 MedAgentBench (NEJM AI, 2025)

**Paper**: "MedAgentBench: A Comprehensive Benchmark for Evaluating Medical AI Agents in Clinical EHR Environments"

**Structure**:
- **Scale**: 300 tasks across 10 categories
- **Data**: Stanford STARR (de-identified EHR data)
- **Standard**: FHIR-compliant task definitions
- **Evaluation**: Multi-step EHR workflow completion

**Task Categories**:
1. Patient lookup & information retrieval
2. Lab order management
3. Medication management
4. Clinical documentation
5. Referral management
6. Diagnostic reasoning
7. Treatment planning
8. Follow-up scheduling
9. Alert management
10. Care coordination

**Paper Organization**:
1. Introduction (EHR agent evaluation gap)
2. Related work
3. Task taxonomy and design
4. FHIR-compliant evaluation framework
5. Experiments (GPT-4, Claude, open-source models)
6. Results (per-category breakdowns)
7. Discussion

**CGA-Bench Differentiation**:
- MedAgentBench evaluates **EHR task completion**; CGA-Bench evaluates **CPG protocol adherence**
- MedAgentBench is broader (10 categories) but shallower per task
- CGA-Bench has temporal reasoning (deadlines, timing) that MedAgentBench lacks
- Cross-benchmark: 5.8% discordant rate (lowest among all benchmarks — closest alignment)
- MedAgentBench uses Stanford STARR; CGA-Bench uses MIMIC-IV

---

### 2.5 MedChain (NeurIPS 2025 Poster)

**Paper**: "MedChain: A Multi-Step Clinical Reasoning Benchmark for Medical AI"

**Structure**:
- **Scale**: 12,163 cases across 19 specialties
- **Design**: 5-stage clinical workflow evaluation
- **Evaluation**: Chain-of-reasoning scoring

**Clinical Workflow Stages**:
1. **History Taking** — Information gathering
2. **Differential Diagnosis** — Hypothesis generation
3. **Investigation** — Test ordering
4. **Diagnosis** — Final diagnosis
5. **Management** — Treatment planning

**CGA-Bench Differentiation**:
- MedChain covers the full clinical workflow; CGA-Bench focuses on **treatment management** (Stage 5 equivalent)
- MedChain emphasizes reasoning chains; CGA-Bench emphasizes protocol compliance
- MedChain has much larger case volume (12,163 vs 180) but less depth per case
- Cross-benchmark: 31.8% discordant rate (highest — MedChain's broader scope creates domain mismatch)
- CGA-Bench's violation taxonomy provides actionable feedback; MedChain's chain scoring is more abstract

---

## 3. Positioning Strategy for Paper

### 3.1 Dimension Comparison Table (for Related Work section)

| Dimension | AgentClinic | HealthBench | MedAgentBench | MedChain | **CGA-Bench** |
|-----------|-------------|-------------|---------------|----------|---------------|
| Temporal reasoning | No | No | Partial | No | **Yes (deadlines, timing)** |
| Violation taxonomy | No | Severity levels | No | No | **5-construct (C1-C5)** |
| CPG-grounded | No | Rubric-based | FHIR tasks | Clinical workflow | **Graph-based CPG** |
| Closed-loop simulation | Yes (dialogue) | No | Partial (EHR) | No | **Yes (environment)** |
| Safety-specific | Partial | Yes (rubric) | No | No | **Yes (forbidden actions)** |
| Statistical rigor | Standard | Inter-rater | Standard | Standard | **Friedman + LOSO + BSR** |

### 3.2 Key Claims to Make

1. **Unique contribution**: CGA-Bench is the **only** benchmark that evaluates temporal CPG adherence with a formal violation taxonomy
2. **Complementary**: Cross-benchmark comparison (17,784 episodes) shows 5.1-31.8% discordant rates, proving CGA-Bench captures safety dimensions other benchmarks miss
3. **Rigorous**: BetterBench-aligned design with Friedman tests, Holm correction, LOSO stability, and BSR discriminant validity
4. **Practical**: 5-construct breakdown (C1-C5) provides actionable feedback for model improvement

### 3.3 Related Work Narrative Structure

```
Paragraph 1: Medical QA benchmarks (MedQA, USMLE, PubMedQA)
  → Limitation: static Q&A, no clinical workflow

Paragraph 2: Clinical agent benchmarks (AgentClinic, MedAgentBench)
  → Progress: interactive, multi-step
  → Limitation: no temporal reasoning, no CPG-grounded evaluation

Paragraph 3: Health evaluation benchmarks (HealthBench, MedChain)
  → Progress: large-scale, multi-domain
  → Limitation: rubric-based or chain-based, no violation taxonomy

Paragraph 4: Benchmark quality standards (BetterBench)
  → Our design follows BetterBench best practices

Paragraph 5: CGA-Bench fills the gap
  → Temporal CPG adherence + violation taxonomy + closed-loop simulation
  → Cross-benchmark validation proves complementary value
```

---

## 4. Cross-Benchmark Discordant Analysis

From `evidence_pack/analysis/cross_comparison_17k.json` (v3, corrected):

| Benchmark | Total Episodes | Discordant | Rate | Primary Cause |
|-----------|---------------|------------|------|---------------|
| AgentClinic | 321 | 40 | 12.5% | Diagnosis vs treatment protocol gap |
| HealthBench | 5,000 | 970 | 19.4% | Over-classification of safety issues (84%) |
| MedChain | 12,163 | 3,868 | 31.8% | Domain mismatch (broad scope) |
| MedAgentBench | 300 | 17 | 5.8% | Closest alignment (EHR task structure) |

**Interpretation**: Lower discordant rate = more aligned evaluation. MedAgentBench's FHIR-based task structure most closely matches CGA-Bench's action-centric evaluation.

---

## 5. BetterBench Self-Audit Checklist

| BetterBench Criterion | CGA-Bench Evidence | Score |
|-----------------------|-------------------|-------|
| Clear construct definition | 5 sub-constructs (C1-C5) | Strong |
| Statistical significance | Friedman p=8.1e-05 (Holm) | Strong |
| Multiple comparison correction | Holm-Bonferroni (family=2) | Strong |
| Stability analysis | LOSO 15/15 significant | Strong |
| Discriminant validity | BSR = 5.1% [1.8%, 8.9%] | Strong |
| Power analysis | N=15 scenarios, power=1.0 | Strong |
| Reproducibility | Fixed seeds, public code | Strong |
| Documentation | Croissant metadata, README | Pending |
| Ethical considerations | MIMIC DUA, no clinical use | Strong |
| Accessibility | GitHub + Zenodo | Pending |
| Maintenance plan | Versioned releases | Pending |

---

*This document is maintained as a positioning reference for the CGA-Bench NeurIPS 2026 submission. Update when new competing benchmarks are published or when cross-benchmark analysis is updated.*
