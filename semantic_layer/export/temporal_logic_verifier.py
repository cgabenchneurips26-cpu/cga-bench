"""
LTL/CTL Formal Verification for Clinical Pathway Traces.

Provides finite-trace LTL and CTL model checking for clinical episode traces.
Verifies temporal properties such as "every lab order is eventually followed by
observation" or "a forbidden medication is never given after a contraindication".

Builds on the existing DECLARE conformance infrastructure by enabling
direct temporal logic formula verification against ActivityEvent sequences.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..conformance.activity import ActivityEvent


# ============================================
# Formula AST
# ============================================

class TemporalOp(Enum):
    """Temporal logic operators."""
    # Propositional
    ATOM = "atom"          # atomic proposition (activity name)
    NOT = "not"            # negation
    AND = "and"            # conjunction
    OR = "or"              # disjunction
    IMPLIES = "implies"    # implication

    # LTL operators
    NEXT = "X"             # neXt state
    FINALLY = "F"          # Finally (eventually)
    GLOBALLY = "G"         # Globally (always)
    UNTIL = "U"            # Until
    WEAK_UNTIL = "W"       # Weak until (release dual)

    # MTL (Metric Temporal Logic) bounded operators
    FINALLY_BOUNDED = "F[]"    # F[a,b](φ): eventually within [a,b] time units
    GLOBALLY_BOUNDED = "G[]"   # G[a,b](φ): always within [a,b] time window
    UNTIL_BOUNDED = "U[]"      # φ U[a,b] ψ: until within [a,b] time bound

    # CTL operators (path quantifiers + temporal)
    EX = "EX"              # Exists neXt
    AX = "AX"              # All neXt
    EF = "EF"              # Exists Finally
    AF = "AF"              # All Finally
    EG = "EG"              # Exists Globally
    AG = "AG"              # All Globally
    EU = "EU"              # Exists Until
    AU = "AU"              # All Until


@dataclass
class TLFormula:
    """Temporal Logic formula (AST node).

    Examples:
        atom("A")                         → activity A occurs at current position
        globally(implies(atom("A"), finally(atom("B"))))  → G(A → F B)
        not_(atom("nitro"))               → ¬nitro
        finally_within(atom("B"), 0, 60)  → F[0,60] B (MTL bounded)
    """
    op: TemporalOp
    atom_name: Optional[str] = None  # For ATOM nodes
    children: List["TLFormula"] = field(default_factory=list)
    time_bound: Optional[Tuple[float, float]] = None  # (lower, upper) in minutes for MTL

    def __repr__(self):
        if self.op == TemporalOp.ATOM:
            return self.atom_name or "?"
        if self.op == TemporalOp.NOT:
            return f"!{self.children[0]}"
        if self.op in (TemporalOp.AND, TemporalOp.OR, TemporalOp.IMPLIES,
                       TemporalOp.UNTIL, TemporalOp.WEAK_UNTIL,
                       TemporalOp.UNTIL_BOUNDED,
                       TemporalOp.EU, TemporalOp.AU):
            op_str = self.op.value
            if self.time_bound:
                op_str = f"{op_str}[{self.time_bound[0]},{self.time_bound[1]}]"
            return f"({self.children[0]} {op_str} {self.children[1]})"
        if self.op in (TemporalOp.FINALLY_BOUNDED, TemporalOp.GLOBALLY_BOUNDED):
            lo, hi = self.time_bound or (0, float('inf'))
            return f"{self.op.value}[{lo},{hi}]({self.children[0]})"
        return f"{self.op.value}({', '.join(str(c) for c in self.children)})"


# ============================================
# Formula Constructors (convenience API)
# ============================================

def atom(name: str) -> TLFormula:
    """Atomic proposition: activity `name` occurs at current position."""
    return TLFormula(op=TemporalOp.ATOM, atom_name=name)


def not_(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.NOT, children=[phi])


def and_(phi: TLFormula, psi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.AND, children=[phi, psi])


def or_(phi: TLFormula, psi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.OR, children=[phi, psi])


def implies(phi: TLFormula, psi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.IMPLIES, children=[phi, psi])


def next_(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.NEXT, children=[phi])


def finally_(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.FINALLY, children=[phi])


def globally(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.GLOBALLY, children=[phi])


def until(phi: TLFormula, psi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.UNTIL, children=[phi, psi])


def weak_until(phi: TLFormula, psi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.WEAK_UNTIL, children=[phi, psi])


# MTL (Metric Temporal Logic) bounded constructors
def finally_within(phi: TLFormula, lo_min: float, hi_min: float) -> TLFormula:
    """F[lo,hi](φ): φ eventually holds within [lo, hi] minutes from current time."""
    return TLFormula(
        op=TemporalOp.FINALLY_BOUNDED,
        children=[phi],
        time_bound=(lo_min, hi_min),
    )


def globally_within(phi: TLFormula, lo_min: float, hi_min: float) -> TLFormula:
    """G[lo,hi](φ): φ holds at all positions within [lo, hi] minutes from current time."""
    return TLFormula(
        op=TemporalOp.GLOBALLY_BOUNDED,
        children=[phi],
        time_bound=(lo_min, hi_min),
    )


def until_within(
    phi: TLFormula, psi: TLFormula, lo_min: float, hi_min: float
) -> TLFormula:
    """φ U[lo,hi] ψ: ψ holds within [lo,hi] minutes, with φ holding until then."""
    return TLFormula(
        op=TemporalOp.UNTIL_BOUNDED,
        children=[phi, psi],
        time_bound=(lo_min, hi_min),
    )


# CTL constructors
def ex(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.EX, children=[phi])


def ax(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.AX, children=[phi])


def ef(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.EF, children=[phi])


def af(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.AF, children=[phi])


def eg(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.EG, children=[phi])


def ag(phi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.AG, children=[phi])


def e_until(phi: TLFormula, psi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.EU, children=[phi, psi])


def a_until(phi: TLFormula, psi: TLFormula) -> TLFormula:
    return TLFormula(op=TemporalOp.AU, children=[phi, psi])


# ============================================
# Verification Results
# ============================================

@dataclass
class VerificationResult:
    """Result of verifying a temporal formula against a trace."""
    formula: TLFormula
    satisfied: bool
    witness_position: Optional[int] = None  # Position where violation/satisfaction found
    counterexample: Optional[List[str]] = None  # Trace prefix as counterexample
    details: str = ""


@dataclass
class PropertySpec:
    """A named clinical safety property with its formula."""
    name: str
    formula: TLFormula
    description: str
    category: str = "safety"  # "safety", "liveness", "fairness"


@dataclass
class VerificationReport:
    """Complete verification report for a trace."""
    trace_id: str
    total_properties: int
    satisfied: int
    violated: int
    results: List[VerificationResult]


# ============================================
# Clinical Property Library
# ============================================

def response_property(trigger: str, response: str) -> PropertySpec:
    """G(trigger → F response): every trigger is eventually followed by response."""
    return PropertySpec(
        name=f"response_{trigger}_to_{response}",
        formula=globally(implies(atom(trigger), finally_(atom(response)))),
        description=f"Every {trigger} must eventually be followed by {response}",
        category="liveness",
    )


def precedence_property(prerequisite: str, action: str) -> PropertySpec:
    """¬action W prerequisite: action never occurs before prerequisite."""
    return PropertySpec(
        name=f"precedence_{prerequisite}_before_{action}",
        formula=weak_until(not_(atom(action)), atom(prerequisite)),
        description=f"{prerequisite} must occur before {action}",
        category="safety",
    )


def absence_property(forbidden: str) -> PropertySpec:
    """G(¬forbidden): forbidden never occurs."""
    return PropertySpec(
        name=f"absence_{forbidden}",
        formula=globally(not_(atom(forbidden))),
        description=f"{forbidden} must never occur",
        category="safety",
    )


def existence_property(required: str) -> PropertySpec:
    """F(required): required must eventually occur."""
    return PropertySpec(
        name=f"existence_{required}",
        formula=finally_(atom(required)),
        description=f"{required} must eventually occur",
        category="liveness",
    )


def not_succession_property(a: str, b: str) -> PropertySpec:
    """G(a → G(¬b)): b never follows a."""
    return PropertySpec(
        name=f"not_succession_{a}_then_{b}",
        formula=globally(implies(atom(a), globally(not_(atom(b))))),
        description=f"{b} must never occur after {a}",
        category="safety",
    )


# ============================================
# MTL Property Library (Time-Bounded)
# ============================================

def response_within_property(
    trigger: str, response: str, max_minutes: float
) -> PropertySpec:
    """G(trigger → F[0,max] response): response must follow trigger within max_minutes.

    Clinical example: "Antibiotics within 60 minutes of blood culture order"
    """
    return PropertySpec(
        name=f"response_{trigger}_to_{response}_within_{int(max_minutes)}min",
        formula=globally(implies(
            atom(trigger),
            finally_within(atom(response), 0.0, max_minutes),
        )),
        description=(
            f"Every {trigger} must be followed by {response} "
            f"within {max_minutes} minutes"
        ),
        category="timing",
    )


def existence_within_property(required: str, max_minutes: float) -> PropertySpec:
    """F[0,max](required): action must occur within max_minutes from trace start.

    Clinical example: "ECG within 10 minutes of arrival"
    """
    return PropertySpec(
        name=f"existence_{required}_within_{int(max_minutes)}min",
        formula=finally_within(atom(required), 0.0, max_minutes),
        description=f"{required} must occur within {max_minutes} minutes",
        category="timing",
    )


def absence_after_property(
    trigger: str, forbidden: str, window_minutes: float
) -> PropertySpec:
    """G(trigger → G[0,window](¬forbidden)): forbidden must not occur within window after trigger.

    Clinical example: "No nitrates within 30 minutes after RV infarct diagnosis"
    """
    return PropertySpec(
        name=f"absence_{forbidden}_after_{trigger}_within_{int(window_minutes)}min",
        formula=globally(implies(
            atom(trigger),
            globally_within(not_(atom(forbidden)), 0.0, window_minutes),
        )),
        description=(
            f"{forbidden} must not occur within {window_minutes} minutes "
            f"after {trigger}"
        ),
        category="safety",
    )


def bounded_response_chain_property(
    a: str, b: str, c: str, ab_max: float, bc_max: float
) -> PropertySpec:
    """G(a → F[0,ab_max](b ∧ F[0,bc_max](c))): chained time-bounded response.

    Clinical example: "Culture → Antibiotics within 60min → Reassess within 360min"
    """
    inner = and_(
        atom(b),
        finally_within(atom(c), 0.0, bc_max),
    )
    return PropertySpec(
        name=f"chain_{a}_{b}_{c}_{int(ab_max)}_{int(bc_max)}min",
        formula=globally(implies(
            atom(a),
            finally_within(inner, 0.0, ab_max),
        )),
        description=(
            f"{a} → {b} within {ab_max}min → {c} within {bc_max}min"
        ),
        category="timing",
    )


# ============================================
# LTL Verifier (Finite Traces)
# ============================================

class LTLVerifier:
    """Verifies LTL formulas on finite traces.

    Uses finite-trace semantics where:
    - F(φ) holds if φ holds at some position i..n
    - G(φ) holds if φ holds at all positions i..n
    - X(φ) holds if φ holds at position i+1 (false at last position)
    - φ U ψ holds if ψ holds at some j≥i and φ holds at all k with i≤k<j
    - φ W ψ = (φ U ψ) ∨ G(φ)

    Ontology Integration (optional):
        When an OntologyMatcher is provided, ATOM evaluation uses subsumption:
        trace[pos] satisfies atom if the action IS-A the atom concept.
        E.g., "GIVE_PIPERACILLIN_TAZOBACTAM" satisfies "GIVE_BROAD_SPECTRUM_ANTIBIOTICS".

    Usage:
        verifier = LTLVerifier()  # strict string matching
        verifier = LTLVerifier(ontology_matcher=matcher)  # subsumption matching
        result = verifier.verify(trace, formula)
    """

    def __init__(self, ontology_matcher=None):
        """Initialize LTL verifier.

        Args:
            ontology_matcher: Optional OntologyMatcher for subsumption-based
                atom evaluation. If None, uses strict string equality.
        """
        self._ontology_matcher = ontology_matcher

    def verify(
        self,
        trace: List[ActivityEvent],
        formula: TLFormula,
    ) -> VerificationResult:
        """Verify an LTL/MTL formula against a trace.

        For MTL bounded operators, uses timestamp_min from ActivityEvent.
        For unbounded LTL operators, only activity names are used.

        Args:
            trace: Ordered list of ActivityEvents
            formula: TLFormula to verify

        Returns:
            VerificationResult with satisfaction status
        """
        if not trace:
            # Empty trace: F(x) is false, G(x) is vacuously true
            sat = self._eval_empty(formula)
            return VerificationResult(
                formula=formula,
                satisfied=sat,
                details="Empty trace",
            )

        trace_names = [e.name for e in trace]
        trace_times = [e.timestamp_min for e in trace]
        satisfied = self._eval(trace_names, 0, formula, trace_times)

        result = VerificationResult(
            formula=formula,
            satisfied=satisfied,
        )

        if not satisfied:
            # Find first violation position
            pos = self._find_violation_position(trace_names, formula, trace_times)
            result.witness_position = pos
            if pos is not None and pos < len(trace_names):
                result.counterexample = trace_names[:pos + 1]
            result.details = f"Violated at position {pos}"

        return result

    def verify_properties(
        self,
        trace: List[ActivityEvent],
        properties: List[PropertySpec],
        trace_id: str = "",
    ) -> VerificationReport:
        """Verify multiple properties against a trace.

        Args:
            trace: ActivityEvent sequence
            properties: List of PropertySpec to verify
            trace_id: Identifier for the trace

        Returns:
            VerificationReport with all results
        """
        results: List[VerificationResult] = []
        for prop in properties:
            result = self.verify(trace, prop.formula)
            results.append(result)

        satisfied = sum(1 for r in results if r.satisfied)
        return VerificationReport(
            trace_id=trace_id,
            total_properties=len(properties),
            satisfied=satisfied,
            violated=len(properties) - satisfied,
            results=results,
        )

    def _eval(
        self,
        trace: List[str],
        pos: int,
        formula: TLFormula,
        times: Optional[List[float]] = None,
    ) -> bool:
        """Recursively evaluate LTL/MTL formula at position `pos` in trace.

        Args:
            trace: Activity names
            pos: Current position
            formula: Formula to evaluate
            times: Optional timestamps (minutes) for MTL bounded operators
        """
        op = formula.op
        n = len(trace)

        if op == TemporalOp.ATOM:
            if pos >= n:
                return False
            if trace[pos] == formula.atom_name:
                return True
            # Ontology subsumption: trace action IS-A formula atom
            if self._ontology_matcher:
                return self._ontology_matcher.satisfies(trace[pos], formula.atom_name)
            return False

        elif op == TemporalOp.NOT:
            return not self._eval(trace, pos, formula.children[0], times)

        elif op == TemporalOp.AND:
            return (self._eval(trace, pos, formula.children[0], times)
                    and self._eval(trace, pos, formula.children[1], times))

        elif op == TemporalOp.OR:
            return (self._eval(trace, pos, formula.children[0], times)
                    or self._eval(trace, pos, formula.children[1], times))

        elif op == TemporalOp.IMPLIES:
            return (not self._eval(trace, pos, formula.children[0], times)
                    or self._eval(trace, pos, formula.children[1], times))

        elif op == TemporalOp.NEXT:
            if pos + 1 >= n:
                return False  # Finite trace: X at last position is false
            return self._eval(trace, pos + 1, formula.children[0], times)

        elif op == TemporalOp.FINALLY:
            # F(φ): ∃j≥pos. φ holds at j
            for j in range(pos, n):
                if self._eval(trace, j, formula.children[0], times):
                    return True
            return False

        elif op == TemporalOp.GLOBALLY:
            # G(φ): ∀j≥pos. φ holds at j
            for j in range(pos, n):
                if not self._eval(trace, j, formula.children[0], times):
                    return False
            return True

        elif op == TemporalOp.UNTIL:
            # φ U ψ: ∃j≥pos. ψ(j) ∧ ∀k∈[pos,j). φ(k)
            phi, psi = formula.children
            for j in range(pos, n):
                if self._eval(trace, j, psi, times):
                    all_phi = all(
                        self._eval(trace, k, phi, times) for k in range(pos, j)
                    )
                    if all_phi:
                        return True
            return False

        elif op == TemporalOp.WEAK_UNTIL:
            # φ W ψ = (φ U ψ) ∨ G(φ)
            u_formula = TLFormula(op=TemporalOp.UNTIL, children=formula.children)
            g_formula = TLFormula(op=TemporalOp.GLOBALLY, children=[formula.children[0]])
            return (self._eval(trace, pos, u_formula, times)
                    or self._eval(trace, pos, g_formula, times))

        # ---- MTL Bounded Operators ----
        elif op == TemporalOp.FINALLY_BOUNDED:
            return self._eval_finally_bounded(trace, pos, formula, times)

        elif op == TemporalOp.GLOBALLY_BOUNDED:
            return self._eval_globally_bounded(trace, pos, formula, times)

        elif op == TemporalOp.UNTIL_BOUNDED:
            return self._eval_until_bounded(trace, pos, formula, times)

        # CTL operators (on linear trace, EX=AX=X, EF=AF=F, etc.)
        elif op in (TemporalOp.EX, TemporalOp.AX):
            return self._eval(trace, pos,
                              TLFormula(op=TemporalOp.NEXT, children=formula.children), times)
        elif op in (TemporalOp.EF, TemporalOp.AF):
            return self._eval(trace, pos,
                              TLFormula(op=TemporalOp.FINALLY, children=formula.children), times)
        elif op in (TemporalOp.EG, TemporalOp.AG):
            return self._eval(trace, pos,
                              TLFormula(op=TemporalOp.GLOBALLY, children=formula.children), times)
        elif op in (TemporalOp.EU, TemporalOp.AU):
            return self._eval(trace, pos,
                              TLFormula(op=TemporalOp.UNTIL, children=formula.children), times)

        return False

    # ---- MTL Bounded Operator Implementations ----

    def _eval_finally_bounded(
        self, trace: List[str], pos: int, formula: TLFormula,
        times: Optional[List[float]],
    ) -> bool:
        """F[lo,hi](φ): ∃j≥pos. lo ≤ (t_j - t_pos) ≤ hi ∧ φ(j)"""
        n = len(trace)
        lo, hi = formula.time_bound or (0.0, float('inf'))
        t_pos = times[pos] if times and pos < len(times) else 0.0

        for j in range(pos, n):
            t_j = times[j] if times and j < len(times) else 0.0
            delta = t_j - t_pos
            if delta > hi:
                break  # Past upper bound, no need to continue
            if delta >= lo and self._eval(trace, j, formula.children[0], times):
                return True
        return False

    def _eval_globally_bounded(
        self, trace: List[str], pos: int, formula: TLFormula,
        times: Optional[List[float]],
    ) -> bool:
        """G[lo,hi](φ): ∀j≥pos. lo ≤ (t_j - t_pos) ≤ hi → φ(j)"""
        n = len(trace)
        lo, hi = formula.time_bound or (0.0, float('inf'))
        t_pos = times[pos] if times and pos < len(times) else 0.0

        for j in range(pos, n):
            t_j = times[j] if times and j < len(times) else 0.0
            delta = t_j - t_pos
            if delta > hi:
                break  # Past window
            if delta >= lo:
                if not self._eval(trace, j, formula.children[0], times):
                    return False
        return True

    def _eval_until_bounded(
        self, trace: List[str], pos: int, formula: TLFormula,
        times: Optional[List[float]],
    ) -> bool:
        """φ U[lo,hi] ψ: ∃j≥pos. lo ≤ (t_j-t_pos) ≤ hi ∧ ψ(j) ∧ ∀k∈[pos,j).φ(k)"""
        n = len(trace)
        lo, hi = formula.time_bound or (0.0, float('inf'))
        t_pos = times[pos] if times and pos < len(times) else 0.0
        phi, psi = formula.children

        for j in range(pos, n):
            t_j = times[j] if times and j < len(times) else 0.0
            delta = t_j - t_pos
            if delta > hi:
                break
            if delta >= lo and self._eval(trace, j, psi, times):
                all_phi = all(
                    self._eval(trace, k, phi, times) for k in range(pos, j)
                )
                if all_phi:
                    return True
        return False

    def _eval_empty(self, formula: TLFormula) -> bool:
        """Evaluate formula on empty trace."""
        op = formula.op
        if op == TemporalOp.ATOM:
            return False
        elif op == TemporalOp.NOT:
            return not self._eval_empty(formula.children[0])
        elif op == TemporalOp.AND:
            return self._eval_empty(formula.children[0]) and self._eval_empty(formula.children[1])
        elif op == TemporalOp.OR:
            return self._eval_empty(formula.children[0]) or self._eval_empty(formula.children[1])
        elif op == TemporalOp.IMPLIES:
            return not self._eval_empty(formula.children[0]) or self._eval_empty(formula.children[1])
        elif op == TemporalOp.GLOBALLY:
            return True  # Vacuously true
        elif op == TemporalOp.FINALLY:
            return False  # Cannot be satisfied
        elif op == TemporalOp.NEXT:
            return False
        elif op == TemporalOp.UNTIL:
            return False  # ψ must hold somewhere
        elif op == TemporalOp.WEAK_UNTIL:
            return True  # G(φ) is vacuously true
        return False

    def _find_violation_position(
        self,
        trace: List[str],
        formula: TLFormula,
        times: Optional[List[float]] = None,
    ) -> Optional[int]:
        """Find the earliest position contributing to violation."""
        op = formula.op
        n = len(trace)

        if op == TemporalOp.GLOBALLY:
            for j in range(n):
                if not self._eval(trace, j, formula.children[0], times):
                    return j
        elif op == TemporalOp.GLOBALLY_BOUNDED:
            lo, hi = formula.time_bound or (0.0, float('inf'))
            t0 = times[0] if times else 0.0
            for j in range(n):
                t_j = times[j] if times and j < len(times) else 0.0
                delta = t_j - t0
                if delta > hi:
                    break
                if delta >= lo and not self._eval(trace, j, formula.children[0], times):
                    return j
        elif op in (TemporalOp.FINALLY, TemporalOp.FINALLY_BOUNDED):
            return n - 1 if n > 0 else 0
        elif op == TemporalOp.NEXT:
            return 0
        elif op in (TemporalOp.UNTIL, TemporalOp.UNTIL_BOUNDED):
            return n - 1 if n > 0 else 0
        elif op == TemporalOp.WEAK_UNTIL:
            phi, psi = formula.children
            for j in range(n):
                if self._eval(trace, j, psi, times):
                    return None
                if not self._eval(trace, j, phi, times):
                    return j
        elif op == TemporalOp.IMPLIES:
            return 0
        elif op == TemporalOp.AND:
            if not self._eval(trace, 0, formula.children[0], times):
                return self._find_violation_position(trace, formula.children[0], times)
            return self._find_violation_position(trace, formula.children[1], times)

        return 0


# ============================================
# CTL Verifier (Kripke Structure)
# ============================================

@dataclass
class KripkeState:
    """A state in the Kripke structure."""
    state_id: int
    labels: Set[str]  # Atomic propositions true in this state
    successors: List[int] = field(default_factory=list)


@dataclass
class KripkeStructure:
    """Kripke structure for CTL model checking."""
    states: List[KripkeState]
    initial_state: int = 0


class CTLVerifier:
    """CTL model checker on Kripke structures built from traces.

    For linear traces (single path), CTL reduces to LTL.
    For branching scenarios (multiple possible continuations),
    builds a proper Kripke structure.

    Usage:
        verifier = CTLVerifier()
        ks = verifier.build_kripke_from_traces(traces)
        result = verifier.verify(ks, formula)
    """

    def build_kripke_from_traces(
        self, traces: List[List[ActivityEvent]]
    ) -> KripkeStructure:
        """Build a Kripke structure from multiple traces.

        Merges common prefixes to create a tree-like structure
        representing all observed behaviors.

        Args:
            traces: List of trace event sequences

        Returns:
            KripkeStructure with merged prefix tree
        """
        if not traces:
            return KripkeStructure(states=[KripkeState(state_id=0, labels=set())])

        # Build prefix tree
        states: List[KripkeState] = [KripkeState(state_id=0, labels={"_start"})]
        state_counter = 1

        for trace in traces:
            current = 0  # Start at root
            trace_names = [e.name for e in trace]

            for i, name in enumerate(trace_names):
                # Check if current state has a successor with this label
                found = False
                for succ_id in states[current].successors:
                    if name in states[succ_id].labels:
                        current = succ_id
                        found = True
                        break

                if not found:
                    # Create new state
                    new_state = KripkeState(
                        state_id=state_counter,
                        labels={name},
                    )
                    states.append(new_state)
                    states[current].successors.append(state_counter)
                    current = state_counter
                    state_counter += 1

        return KripkeStructure(states=states, initial_state=0)

    def verify(
        self,
        kripke: KripkeStructure,
        formula: TLFormula,
        start_state: Optional[int] = None,
    ) -> VerificationResult:
        """Verify a CTL formula on a Kripke structure.

        Args:
            kripke: KripkeStructure to verify against
            formula: CTL formula
            start_state: State to start verification (default: initial)

        Returns:
            VerificationResult
        """
        start = start_state if start_state is not None else kripke.initial_state
        sat_set = self._compute_sat_set(kripke, formula)
        satisfied = start in sat_set

        return VerificationResult(
            formula=formula,
            satisfied=satisfied,
            details=f"Satisfied in {len(sat_set)}/{len(kripke.states)} states",
        )

    def _compute_sat_set(
        self, ks: KripkeStructure, formula: TLFormula
    ) -> Set[int]:
        """Compute the set of states satisfying the formula."""
        op = formula.op
        all_states = set(range(len(ks.states)))

        if op == TemporalOp.ATOM:
            return {
                s.state_id for s in ks.states
                if formula.atom_name in s.labels
            }

        elif op == TemporalOp.NOT:
            child_sat = self._compute_sat_set(ks, formula.children[0])
            return all_states - child_sat

        elif op == TemporalOp.AND:
            left = self._compute_sat_set(ks, formula.children[0])
            right = self._compute_sat_set(ks, formula.children[1])
            return left & right

        elif op == TemporalOp.OR:
            left = self._compute_sat_set(ks, formula.children[0])
            right = self._compute_sat_set(ks, formula.children[1])
            return left | right

        elif op == TemporalOp.IMPLIES:
            left = self._compute_sat_set(ks, formula.children[0])
            right = self._compute_sat_set(ks, formula.children[1])
            return (all_states - left) | right

        elif op == TemporalOp.EX:
            child_sat = self._compute_sat_set(ks, formula.children[0])
            return {
                s.state_id for s in ks.states
                if any(succ in child_sat for succ in s.successors)
            }

        elif op == TemporalOp.AX:
            child_sat = self._compute_sat_set(ks, formula.children[0])
            return {
                s.state_id for s in ks.states
                if s.successors and all(succ in child_sat for succ in s.successors)
            }

        elif op == TemporalOp.EF:
            # EF φ = φ ∨ EX(EF φ) — fixed point
            return self._least_fixpoint_ef(ks, formula.children[0])

        elif op == TemporalOp.AF:
            # AF φ = φ ∨ AX(AF φ) — fixed point
            return self._least_fixpoint_af(ks, formula.children[0])

        elif op == TemporalOp.EG:
            # EG φ = φ ∧ EX(EG φ) — greatest fixed point
            return self._greatest_fixpoint_eg(ks, formula.children[0])

        elif op == TemporalOp.AG:
            # AG φ = φ ∧ AX(AG φ) — greatest fixed point
            return self._greatest_fixpoint_ag(ks, formula.children[0])

        elif op == TemporalOp.EU:
            # E[φ U ψ] — least fixed point
            phi_sat = self._compute_sat_set(ks, formula.children[0])
            psi_sat = self._compute_sat_set(ks, formula.children[1])
            return self._least_fixpoint_eu(ks, phi_sat, psi_sat)

        elif op == TemporalOp.AU:
            # A[φ U ψ] — least fixed point
            phi_sat = self._compute_sat_set(ks, formula.children[0])
            psi_sat = self._compute_sat_set(ks, formula.children[1])
            return self._least_fixpoint_au(ks, phi_sat, psi_sat)

        # LTL operators on Kripke: treat as CTL equivalents
        elif op == TemporalOp.NEXT:
            return self._compute_sat_set(ks, ax(formula.children[0]))
        elif op == TemporalOp.FINALLY:
            return self._compute_sat_set(ks, af(formula.children[0]))
        elif op == TemporalOp.GLOBALLY:
            return self._compute_sat_set(ks, ag(formula.children[0]))
        elif op == TemporalOp.UNTIL:
            return self._compute_sat_set(ks, a_until(formula.children[0], formula.children[1]))
        elif op == TemporalOp.WEAK_UNTIL:
            # W = U ∨ G
            u_sat = self._compute_sat_set(ks, a_until(formula.children[0], formula.children[1]))
            g_sat = self._compute_sat_set(ks, ag(formula.children[0]))
            return u_sat | g_sat

        return set()

    def _least_fixpoint_ef(self, ks: KripkeStructure, phi: TLFormula) -> Set[int]:
        """EF φ: states that can reach a φ-state."""
        phi_sat = self._compute_sat_set(ks, phi)
        result = set(phi_sat)
        changed = True
        while changed:
            changed = False
            for s in ks.states:
                if s.state_id not in result:
                    if any(succ in result for succ in s.successors):
                        result.add(s.state_id)
                        changed = True
        return result

    def _least_fixpoint_af(self, ks: KripkeStructure, phi: TLFormula) -> Set[int]:
        """AF φ: states from which all paths reach φ."""
        phi_sat = self._compute_sat_set(ks, phi)
        result = set(phi_sat)
        changed = True
        while changed:
            changed = False
            for s in ks.states:
                if s.state_id not in result:
                    # All successors in result (or no successors = terminal)
                    if s.successors and all(succ in result for succ in s.successors):
                        result.add(s.state_id)
                        changed = True
                    elif not s.successors:
                        # Terminal state: AF holds only if phi holds here
                        pass  # Already handled by phi_sat
        return result

    def _greatest_fixpoint_eg(self, ks: KripkeStructure, phi: TLFormula) -> Set[int]:
        """EG φ: states with some path where φ always holds."""
        phi_sat = self._compute_sat_set(ks, phi)
        result = set(phi_sat)
        changed = True
        while changed:
            changed = False
            to_remove = set()
            for sid in result:
                s = ks.states[sid]
                # Must have at least one successor in result, or be terminal
                if s.successors and not any(succ in result for succ in s.successors):
                    to_remove.add(sid)
                    changed = True
            result -= to_remove
        return result

    def _greatest_fixpoint_ag(self, ks: KripkeStructure, phi: TLFormula) -> Set[int]:
        """AG φ: states where all reachable states satisfy φ."""
        phi_sat = self._compute_sat_set(ks, phi)
        result = set(phi_sat)
        changed = True
        while changed:
            changed = False
            to_remove = set()
            for sid in result:
                s = ks.states[sid]
                if s.successors and not all(succ in result for succ in s.successors):
                    to_remove.add(sid)
                    changed = True
            result -= to_remove
        return result

    def _least_fixpoint_eu(
        self, ks: KripkeStructure, phi_sat: Set[int], psi_sat: Set[int]
    ) -> Set[int]:
        """E[φ U ψ]: there exists a path where φ holds until ψ holds."""
        result = set(psi_sat)
        changed = True
        while changed:
            changed = False
            for s in ks.states:
                if s.state_id not in result and s.state_id in phi_sat:
                    if any(succ in result for succ in s.successors):
                        result.add(s.state_id)
                        changed = True
        return result

    def _least_fixpoint_au(
        self, ks: KripkeStructure, phi_sat: Set[int], psi_sat: Set[int]
    ) -> Set[int]:
        """A[φ U ψ]: on all paths, φ holds until ψ holds."""
        result = set(psi_sat)
        changed = True
        while changed:
            changed = False
            for s in ks.states:
                if s.state_id not in result and s.state_id in phi_sat:
                    if s.successors and all(succ in result for succ in s.successors):
                        result.add(s.state_id)
                        changed = True
                    elif not s.successors:
                        pass  # Terminal: AU requires ψ to hold
        return result
