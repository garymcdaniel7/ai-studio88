"""Èṣù — Communication, Routing, Tool Dispatch, Coordination.

Èṣù is the gateway agent. Every request passes through Èṣù first.
It determines:
- Which other agents should be consulted
- Which tools are relevant
- How to route the request
- When to invoke actions vs just respond

Èṣù does NOT do the creative thinking — it delegates to specialists.
Think of Èṣù as the intelligent dispatcher / switchboard operator.
"""

from __future__ import annotations

import logging

from backend.aios.council.base import (
    AgentDecision,
    AIOSContext,
    AuthorityLevel,
    Capability,
    CouncilAgent,
    ProposedAction,
    ActionResult,
)

logger = logging.getLogger(__name__)

# Intent keywords mapped to relevant agents and tools
INTENT_MAP = {
    "generate": {"agents": ["òrúnmìlà"], "tools": ["generate_image", "generate_video"]},
    "create": {"agents": ["òrúnmìlà"], "tools": ["generate_image", "create_talent"]},
    "image": {"agents": ["òrúnmìlà"], "tools": ["generate_image"]},
    "video": {"agents": ["òrúnmìlà"], "tools": ["generate_video"]},
    "train": {"agents": ["òrúnmìlà"], "tools": ["train_lora"]},
    "lora": {"agents": ["òrúnmìlà"], "tools": ["train_lora"]},
    "publish": {"agents": ["òrúnmìlà"], "tools": ["schedule_post"]},
    "schedule": {"agents": ["òrúnmìlà"], "tools": ["schedule_post"]},
    "voice": {"agents": ["òrúnmìlà"], "tools": ["generate_voice"]},
    "music": {"agents": ["òrúnmìlà"], "tools": ["generate_music"]},
    "health": {"agents": ["ọbalúayé"], "tools": ["check_health"]},
    "status": {"agents": ["ọbalúayé"], "tools": ["check_health"]},
    "worker": {"agents": ["ọbalúayé"], "tools": ["worker_status"]},
    "gpu": {"agents": ["ọbalúayé"], "tools": ["worker_status", "launch_worker"]},
    "cost": {"agents": ["ọbalúayé"], "tools": ["cost_summary"]},
    "budget": {"agents": ["ọbalúayé"], "tools": ["cost_summary"]},
    "model": {"agents": ["òrúnmìlà"], "tools": ["list_models", "recommend_model"]},
    "prompt": {"agents": ["òrúnmìlà"], "tools": ["enhance_prompt"]},
    "story": {"agents": ["òrúnmìlà"], "tools": ["continue_story"]},
    "campaign": {"agents": ["òrúnmìlà"], "tools": ["create_campaign"]},
    "talent": {"agents": ["òrúnmìlà"], "tools": ["search_talent"]},
}


class Esu(CouncilAgent):
    """Èṣù — the communication and routing agent."""

    @property
    def name(self) -> str:
        return "èṣù"

    @property
    def display_name(self) -> str:
        return "Èṣù"

    @property
    def domain(self) -> str:
        return "Communication, routing, tool selection, agent coordination"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.EXECUTE_READ

    def capabilities(self) -> list[Capability]:
        return [
            Capability("route_request", "Analyze intent and route to appropriate agents/tools"),
            Capability("discover_tools", "List available platform tools for a given intent"),
            Capability("coordinate_agents", "Orchestrate multi-agent collaboration"),
        ]

    def relevance_score(self, context: AIOSContext) -> float:
        return 1.0  # Èṣù is always relevant — it's the router

    async def reason(self, context: AIOSContext) -> AgentDecision:
        """Analyze the user's intent and determine routing."""
        message = context.user_message.lower()

        # Identify relevant agents and tools
        relevant_agents = set()
        relevant_tools = set()

        for keyword, mapping in INTENT_MAP.items():
            if keyword in message:
                relevant_agents.update(mapping["agents"])
                relevant_tools.update(mapping["tools"])

        # If nothing matched, default to general chat (no tools needed)
        if not relevant_agents:
            return AgentDecision(
                agent=self.name,
                summary="General conversation — no specific tools needed",
                reasoning="No action-oriented intent detected. Routing to conversational response.",
                confidence=0.7,
                metadata={
                    "intent": "chat",
                    "relevant_agents": [],
                    "relevant_tools": [],
                },
            )

        # Determine if this is an action request or an information request
        action_words = {"create", "generate", "make", "build", "train", "publish", "schedule", "launch", "start", "delete", "remove"}
        is_action = any(word in message for word in action_words)

        # Build proposed actions if it's an action request
        actions = []
        if is_action and relevant_tools:
            primary_tool = list(relevant_tools)[0]
            actions.append(ProposedAction(
                tool=primary_tool,
                parameters={"user_request": context.user_message},
                reasoning=f"User requested action matching '{primary_tool}'",
                confidence=0.75,
                requires_approval=primary_tool in ("train_lora", "launch_worker", "schedule_post"),
            ))

        return AgentDecision(
            agent=self.name,
            summary=f"Routing to {', '.join(relevant_agents)} with tools: {', '.join(relevant_tools)}",
            reasoning=f"Intent analysis: {'action' if is_action else 'information'} request. "
                      f"Keywords matched: {[k for k in INTENT_MAP if k in message]}",
            confidence=0.85,
            proposed_actions=actions,
            metadata={
                "intent": "action" if is_action else "information",
                "relevant_agents": list(relevant_agents),
                "relevant_tools": list(relevant_tools),
                "is_action_request": is_action,
            },
        )

    async def execute(self, action: ProposedAction) -> ActionResult:
        """Èṣù can execute read-only tool discovery and routing."""
        if action.tool == "discover_tools":
            from backend.brain.registry import list_modules
            return ActionResult(success=True, output=list_modules())

        return ActionResult(success=False, error=f"Èṣù cannot execute '{action.tool}' directly")
