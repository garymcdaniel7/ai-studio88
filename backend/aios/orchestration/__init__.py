"""AIOS Session Orchestration — multi-worker session management.

Manages intelligent allocation of GPU workers based on session type.
One session may span multiple workers (image + video + training).

Key concepts:
- Session Planning: AI asks what kind of session before allocating
- Worker Selection: picks best provider/GPU based on task
- Model Placement: keeps hot models loaded, swaps intelligently
- Auto-scaling: provisions on demand, releases when idle
- Budget awareness: respects daily caps
"""
