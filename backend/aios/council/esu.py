"""Esu — Communication, Routing, Tool Dispatch, Coordination.

Esu is the gateway agent. Every request passes through Esu first.
It determines:
- Which other agents should be consulted
- Which tools are relevant
- How to route the request
- When to invoke actions vs just respond

Esu does NOT do the creative thinking — it delegates to specialists.
Think of Esu as the intelligent dispatcher / switchboard operator.
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
    "generate": {"agents": ["orunmila"], "tools": ["generate_image", "generate_video"]},
    "create": {"agents": ["orunmila"], "tools": ["generate_image", "create_talent"]},
    "image": {"agents": ["orunmila"], "tools": ["generate_image"]},
    "video": {"agents": ["orunmila"], "tools": ["generate_video"]},
    "train": {"agents": ["orunmila"], "tools": ["train_lora"]},
    "lora": {"agents": ["orunmila"], "tools": ["train_lora"]},
    "publish": {"agents": ["orunmila"], "tools": ["schedule_post"]},
    "schedule": {"agents": ["orunmila"], "tools": ["schedule_post"]},
    "voice": {"agents": ["orunmila"], "tools": ["generate_voice"]},
    "music": {"agents": ["orunmila"], "tools": ["generate_music"]},
    "health": {"agents": ["obaluaye"], "tools": ["check_health"]},
    "status": {"agents": ["obaluaye"], "tools": ["check_health"]},
    "worker": {"agents": ["obaluaye"], "tools": ["worker_status"]},
    "gpu": {"agents": ["obaluaye"], "tools": ["worker_status", "launch_worker"]},
    "cost": {"agents": ["obaluaye"], "tools": ["cost_summary"]},
    "budget": {"agents": ["obaluaye"], "tools": ["cost_summary"]},
    "model": {"agents": ["orunmila"], "tools": ["list_models", "recommend_model"]},
    "prompt": {"agents": ["orunmila"], "tools": ["enhance_prompt"]},
    "story": {"agents": ["orunmila"], "tools": ["continue_story"]},
    "campaign": {"agents": ["orunmila"], "tools": ["create_campaign"]},
    "talent": {"agents": ["orunmila"], "tools": ["search_talent"]},
}


class Esu(CouncilAgent):
    """Esu — the communication and routing agent."""

    @property
    def name(self) -> str:
        return "esu"

    @property
    def display_name(self) -> str:
        return "Esu"

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
        return 1.0  # Esu is always relevant — it's the router

    async def reason(self, context: AIOSContext) -> AgentDecision:
        """Analyze the user's intent and determine routing."""
        from backend.aios.agent_dna import get_agent_dna

        message = context.user_message.lower()

        # Identify relevant agents and tools
        relevant_agents = set()
        relevant_tools = set()

        for keyword, mapping in INTENT_MAP.items():
            if keyword in message:
                relevant_agents.update(mapping["agents"])
                relevant_tools.update(mapping["tools"])

        # If nothing matched, try LLM-based intent detection
        if not relevant_agents:
            try:
                from backend.aios.provider_router import route_request, RoutingContext
                from backend.aios.agent_dna import get_agent_dna

                intent_prompt = get_agent_dna("esu") + "\n\nClassify this user message. Is it an ACTION request (generate, train, publish, etc.) or just CHAT? If action, what tool? Respond with just: CHAT or ACTION:<tool_name>"
                msgs = [{"role": "system", "content": intent_prompt}, {"role": "user", "content": message}]
                rctx = RoutingContext(mode="production_advisor", message_length=len(message))
                response, _, _ = route_request(msgs, rctx)
                resp_lower = response.strip().lower()

                if "action:" in resp_lower:
                    tool = resp_lower.split("action:")[1].strip().split()[0]
                    if tool in INTENT_MAP or tool in ("generate_image", "train_lora", "generate_video"):
                        relevant_agents.add("orunmila")
                        relevant_tools.add(tool)
            except Exception:
                pass  # LLM intent detection is optional enhancement

        # If still nothing matched, default to general chat
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
        """Esu can execute read-only tool discovery and routing."""
        if action.tool == "discover_tools":
            from backend.brain.registry import list_modules
            return ActionResult(success=True, output=list_modules())

        return ActionResult(success=False, error=f"Esu cannot execute '{action.tool}' directly")
