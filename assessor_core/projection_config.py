"""ProjectionConfig: toggles for EX-D1 projection operator ablation."""

from dataclasses import dataclass


@dataclass
class ProjectionConfig:
    """Controls which projection operators are active in the scoring pipeline.

    Each flag corresponds to one of the four projection operators
    from Theorem 3.4. Default True preserves existing behavior.
    """

    apply_terminology: bool = True  # pi_term: ActionNormalizer both-side normalization
    apply_action_set: bool = True  # pi_aset: domain detection heuristic
    apply_numeric_context: bool = True  # pi_nctx: CPG_OVERSPECIFIC guard
    apply_numeric_timing: bool = True  # pi_ntim: consumed set 1:1 matching

    @property
    def config_id(self) -> str:
        """Short identifier like 'T1_A1_C1_N1' for this config."""
        bits = [
            f"T{int(self.apply_terminology)}",
            f"A{int(self.apply_action_set)}",
            f"C{int(self.apply_numeric_context)}",
            f"N{int(self.apply_numeric_timing)}",
        ]
        return "_".join(bits)

    @staticmethod
    def all_configs() -> list["ProjectionConfig"]:
        """Generate all 2^4 = 16 projection configs."""
        configs = []
        for t in (False, True):
            for a in (False, True):
                for c in (False, True):
                    for n in (False, True):
                        configs.append(
                            ProjectionConfig(
                                apply_terminology=t,
                                apply_action_set=a,
                                apply_numeric_context=c,
                                apply_numeric_timing=n,
                            )
                        )
        return configs
