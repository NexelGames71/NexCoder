"""Agent Mesh: one orchestrator coordinating bounded specialist agents.

Phase 1 scope (see docs/superpowers/specs — mesh roadmap): work-unit
decomposition, sequential dependency-ordered execution over the v2
AgentLoop, structured mesh events, conflict detection, budgets,
cancellation, and one synthesized final report. Model inference is
serialized by design — the local GGUF server runs one request at a time.
"""
