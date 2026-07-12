"""Hermes Agent Integration — the actual Nous Research Hermes agent.

Hermes provides:
- Self-improving skills (learns from successful interactions)
- Persistent memory across sessions
- 70+ built-in tools (terminal, browser, web, file, vision)
- Multi-provider LLM support
- Conversation loop with tool calling
- MCP integration

We embed Hermes as the proactive orchestration layer for AI Studio.
It handles:
- Complex multi-step tasks that require tool use
- Self-improving workflows (creates skills from success)
- Cross-session memory (remembers user preferences)
- Autonomous background operations (when approved)
"""
