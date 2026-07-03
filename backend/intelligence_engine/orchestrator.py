"""Intelligence Orchestrator — runs all agents and assembles creative plan.

This is the main entry point for the Intelligence Engine.
It builds context, runs all agents, and produces a unified CreativePlan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.intelligence_engine.context import IntelligenceContext, build_context_from_request
from backend.intelligence_engine.agents.base import BaseAgent, AgentOutput
from backend.intelligence_engine.agents.creative_director import CreativeDirector
from backend.intelligence_engine.agents.prompt_engineer import PromptEngineer
from backend.intelligence_engine.agents.model_expert import ModelExpert
from backend.intelligence_engine.agents.workflow_optimizer import WorkflowOptimizer
from backend.intelligence_engine.agents.gpu_optimizer import GPUOptimizer
from backend.intelligence_engine.agents.continuity_director import ContinuityDirector
from backend.intelligence_engine.agents.story_director import StoryDirector
from backend.intelligence_engine.agents.video_director import VideoDirector
from backend.intelligence_engine.agents.publishing_advisor import PublishingAdvisor
from backend.intelligence_engine.agents.learning_engine import LearningEngine


@dataclass
class CreativePlan:
    """Complete creative plan assembled from all agent outputs."""
    # Assembled outputs
    prompt: str = ""
    negative_prompt: str = ""
    model: str = "flux-dev"
    settings: dict = field(default_factory=dict)
    workflow_steps: list[dict] = field(default_factory=list)
    gpu_routing: dict = field(default_factory=dict)

    # Agent outputs (for display / reasoning)
    agent_outputs: list[AgentOutput] = field(default_factory=list)

    # Metadata
    session_id: str = ""
    talent_id: str = ""
    content_type: str = "image"
    platform: str = "instagram"
    confidence: float = 0.0

    # Publishing
    publishing: dict = field(default_factory=dict)

    # Estimates
    estimated_time: str = ""
    estimated_cost: str = ""


# =============================================================================
# Agent Registry
# =============================================================================
# All agents run in this order. Each reads context independently.
# To add a new agent: create the class, add it here.

AGENTS: list[type[BaseAgent]] = [
    CreativeDirector,
    PromptEngineer,
    ModelExpert,
    WorkflowOptimizer,
    GPUOptimizer,
    ContinuityDirector,
    StoryDirector,
    VideoDirector,
    PublishingAdvisor,
    LearningEngine,
]


def run_agents(context: IntelligenceContext) -> list[AgentOutput]:
    """Run all registered agents against the given context.

    Each agent runs independently — no agent depends on another's output.
    """
    outputs = []
    for agent_class in AGENTS:
        agent = agent_class()
        try:
            output = agent.think(context)
            outputs.append(output)
        except Exception as e:
            outputs.append(AgentOutput(
                agent=agent.name,
                recommendations=[{"title": "Error", "content": str(e), "type": "error"}],
                reasoning=f"Agent failed: {e}",
                confidence=0.0,
            ))
    return outputs


def build_creative_plan(
    user_idea: str,
    talent_id: str | None = None,
    project_id: str | None = None,
    platform: str = "instagram",
    content_type: str = "image",
    campaign: str = "",
    target_audience: str = "",
) -> CreativePlan:
    """Build a complete creative plan by running all agents.

    This is the primary API for the Intelligence Engine.

    Returns a CreativePlan with prompt, model, workflow, GPU routing,
    publishing advice, and all agent reasoning.
    """
    # Build rich context from DB
    context = build_context_from_request(
        user_idea=user_idea,
        talent_id=talent_id,
        project_id=project_id,
        platform=platform,
        content_type=content_type,
        campaign=campaign,
        target_audience=target_audience,
    )

    # Run all agents
    agent_outputs = run_agents(context)

    # Assemble the plan from agent outputs
    plan = CreativePlan(
        session_id=context.session_id,
        talent_id=talent_id or "",
        content_type=content_type,
        platform=platform,
        agent_outputs=agent_outputs,
    )

    # Extract structured data from agent metadata
    for output in agent_outputs:
        if output.agent == "Prompt Engineer":
            plan.prompt = output.metadata.get("positive_prompt", "")
            plan.negative_prompt = output.metadata.get("negative_prompt", "")

        elif output.agent == "Model Expert":
            plan.model = output.metadata.get("model", "flux-dev")
            plan.settings = output.metadata.get("settings", {})

        elif output.agent == "Workflow Optimizer":
            plan.workflow_steps = output.metadata.get("steps", [])
            plan.estimated_time = f"~{output.metadata.get('total_seconds', 60)}s"

        elif output.agent == "GPU Optimizer":
            plan.gpu_routing = output.metadata
            plan.estimated_cost = output.metadata.get("cost", "~$0.02")

        elif output.agent == "Publishing Advisor":
            plan.publishing = {
                r["type"]: r["content"]
                for r in output.recommendations
                if r.get("type") not in ("skip",)
            }

    # Overall confidence = average of all agents
    confidences = [o.confidence for o in agent_outputs if o.confidence > 0]
    plan.confidence = sum(confidences) / len(confidences) if confidences else 0.5

    return plan
