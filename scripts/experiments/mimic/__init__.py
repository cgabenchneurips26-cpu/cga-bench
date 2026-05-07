"""MIMIC-IV camera-ready augmentation pipeline (App AQ.1-AQ.3).

See docs/impl/mimic_datset_exp.md and KNOWN_ISSUES.md §6 for context.
Each phase script under this package writes a `*.summary.json` next to its
output, with the keys required by the source contract:
    n_episodes, n_excluded, exclusion_breakdown, seed, git_sha,
    mimic_version, wall_time_s.
"""
