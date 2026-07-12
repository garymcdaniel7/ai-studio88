"""Council Orchestrator — runs relevant agents and assembles decisions.

The orchestrator:
1. Receives a request via AIOSContext
2. Asks Èṣù to route it (which agents/tools are relevant?)
3. Runs relevant agents in parallel
4. Assembles decisions into a unified response
5. Checks governance (any actions need approval?)
6. Returns the final decision

This replaces both:
- intelligence_engine/orchestrator.py (run_agents → build_creative_plan)
- autonomous_studio/orchestrator.py (run_all_departments → daily_briefing)
"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.aios.council.base import (
    AgentDecision,
    AIOSContext,
    CouncilAgent,
)
from backend.aios.council.esu import Esu
from backend.aios.council.orunmila import Orunmila

logger = logging.getLogger(__name__)


# =============================================================================
# Agent Registry
# =============================================================================

COUNCIL_AGENTS: list[type[CouncilAgent]] = [
    Esu,
    Orunmila,
    # Future: Obaluaye, Ogun, Osun, Oya, Yemoja, Sango, Aje
]


def get_all_agents() -> list[CouncilAgent]:
    """Instantiate all registered council agents."""
    return [cls() for cls in COUNCIL_AGENTS]


# =============================================================================
# Council Orchestration
# =============================================================================


async def run_council(context: AIOSContext) -> dict:
    """Run the agent council on a given context.

    Flow:
    1. Èṣù analyzes intent and routes
    2. Relevant agents reason over context
    3. Decisions assembled into unified response
    4. Governance checks applied

    Returns a dict with:
    - decisions: list of AgentDecision
    - routing: Èṣù's routing analysis
    - proposed_actions: all proposed actions (for approval)
    - summary: unified summary
    """
    start = time.time()
    agents = get_all_agents()

    # Step 1: Èṣù routes the request
    esu = next(a for a in agents if a.name == "èṣù")
    routing_decision = await esu.reason(context)

    # Step 2: Determine which agents to consult
    relevant_agent_names = set(routing_decision.metadata.get("relevant_agents", []))
    # Always include Èṣù's decision
    all_decisions = [routing_decision]

    # Step 3: Run relevant agents
    other_agents = [a for a in agents if a.name != "èṣù"]

    for agent in other_agents:
        # Skip if not relevant (based on Èṣù's routing)
        if relevant_agent_names and agent.name not in relevant_agent_names:
            # Still check relevance score as fallback
            if agent.relevance_score(context) < 0.4:
                continue

        try:
            decision = await agent.reason(context)
            all_decisions.append(decision)
        except Exception as e:
            logger.warning(f"Agent {agent.name} failed: {e}")
            all_decisions.append(AgentDecision(
                agent=agent.name,
                summary=f"Error: {str(e)[:100]}",
                confidence=0.0,
            ))

    # Step 4: Assemble all proposed actions
    all_actions = []
    for decision in all_decisions:
        all_actions.extend(decision.proposed_actions)

    # Step 5: Apply governance to all proposed actions
    governance_result = {}
    if all_actions:
        try:
            from backend.aios.governance.middleware import apply_governance

            governance_result = apply_governance(
                actions=all_actions,
                session_id=context.session_id,
            )
        except Exception as e:
            logger.warning(f"Governance middleware failed: {e}")
            governance_result = {"auto_approved": [], "pending_approval": [], "blocked": []}

    # Step 6: Build unified summary
    summaries = [d.summary for d in all_decisions if d.summary and d.confidence > 0.3]
    unified_summary = " → ".join(summaries) if summaries else "No specific actions identified."

    elapsed = time.time() - start

    return {
        "decisions": [
            {
                "agent": d.agent,
                "summary": d.summary,
                "reasoning": d.reasoning,
                "confidence": d.confidence,
                "actions": [
                    {
                        "tool": a.tool,
                        "parameters": a.parameters,
                        "reasoning": a.reasoning,
                        "confidence": a.confidence,
                        "requires_approval": a.requires_approval,
                        "estimated_cost_usd": a.estimated_cost_usd,
                    }
                    for a in d.proposed_actions
                ],
            }
            for d in all_decisions
        ],
        "routing": {
            "intent": routing_decision.metadata.get("intent", "unknown"),
            "relevant_agents": list(relevant_agent_names),
            "relevant_tools": routing_decision.metadata.get("relevant_tools", []),
        },
        "proposed_actions": [
            {
                "tool": a.tool,
                "parameters": a.parameters,
                "reasoning": a.reasoning,
                "confidence": a.confidence,
                "requires_approval": a.requires_approval,
                "estimated_cost_usd": a.estimated_cost_usd,
                "estimated_time_seconds": a.estimated_time_seconds,
            }
            for a in all_actions
        ],
        "summary": unified_summary,
        "agents_consulted": [d.agent for d in all_decisions],
        "governance": governance_result,
        "elapsed_ms": int(elapsed * 1000),
    }
