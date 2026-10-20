"""Simulator backend (F07, T2): controllable clock, scenario runs, dispatch.

The simulator drives the real deterministic core through the same persisted
dispatch path the HireDesk webhook uses. It adds three simulator-only
concerns: a clock that can be advanced (its offset is persisted per run), a
scenario run store holding the scripted core snapshot between requests, and
scenario definitions D1-D7.
"""
