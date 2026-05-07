"""External scorer adapters for CRES-3 native replay defense.

Each module here translates CGA-Bench `EpisodeLog` / cached verdict records
into the input format expected by an external benchmark's own scoring code
(MedAgentBench, AgentClinic, AMEGA). The defense goal: show that those
authors' own scorers agree with our proxy implementations on identical
traces, rebutting the "straw-man evaluator" attack.
"""
