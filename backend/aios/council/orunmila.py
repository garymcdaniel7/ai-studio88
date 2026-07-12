"""Orunmila — Chief Intelligence, Planning, Reasoning, Strategy.

Orunmila is the thinking agent. It takes Esu's routing decision and:
- Creates detailed execution plans
- Reasons about the best approach
- Considers Creative DNA, project context, and history
- Proposes multi-step workflows
- Estimates costs and time

Orunmila uses the LLM for reasoning (unlike Esu which is rule-based).
It produces plans that Esu then coordinates execution of.
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
)

logger = logging.getLogger(__name__)


class Orunmila(CouncilAgent):
    """Orunmila — the planning and reasoning agent."""

    @property
    def name(self) -> str:
        return "orunmila"

    @property
    def display_name(self) -> str:
        return "Orunmila"

    @property
    def domain(self) -> str:
        return "Planning, reasoning, strategy, long-term orchestration"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.RECOMMEND  # Proposes plans, never executes directly

    def capabilities(self) -> list[Capability]:
        return [
            Capability("create_plan", "Decompose a request into executable steps"),
            Capability("recommend_workflow", "Suggest optimal generation workflow"),
            Capability("estimate_cost", "Estimate GPU/API cost for a plan"),
            Capability("recommend_model", "Pick best model for a task"),
            Capability("enhance_prompt", "Optimize a generation prompt"),
        ]

    def relevance_score(self, context: AIOSContext) -> float:
        """Highly relevant for action requests, less for simple chat."""
        msg = context.user_message.lower()
        action_indicators = [
            "create", "generate", "make", "build", "plan", "how to",
            "recommend", "suggest", "what model", "best way", "optimize",
            "train", "produce", "publish", "schedule",
        ]
        matches = sum(1 for word in action_indicators if word in msg)
        return min(0.3 + matches * 0.2, 1.0)

    async def reason(self, context: AIOSContext) -> AgentDecision:
        """Create an intelligent plan using LLM reasoning.

        Falls back to rule-based planning if LLM is unavailable.
        """
        message = context.user_message

        # Try LLM-powered planning
        try:
            plan = await self._llm_plan(context)
            if plan:
                return plan
        except Exception as e:
            logger.warning(f"Orunmila LLM planning failed: {e}")

        # Fallback to rule-based planning (enhanced version of brain/planner.py)
        return self._rule_based_plan(context)

    async def _llm_plan(self, context: AIOSContext) -> AgentDecision | None:
        """Use LLM to create a plan (when available)."""
        from backend.aios.provider_router import route_request, RoutingContext

        planning_prompt = self._build_planning_prompt(context)

        messages = [
            {"role": "system", "content": planning_prompt},
            {"role": "user", "content": context.user_message},
        ]

        routing_ctx = RoutingContext(
            mode="production_advisor",
            message_length=len(context.user_message),
            session_message_count=0,
        )

        try:
            response, provider, model = route_request(messages, routing_ctx)
        except Exception:
            return None

        # Parse the LLM response into structured actions
        actions = self._parse_plan_response(response, context)

        return AgentDecision(
            agent=self.name,
            summary=f"Plan created ({len(actions)} steps)",
            reasoning=response[:500],
            confidence=0.8,
            proposed_actions=actions,
            metadata={
                "planning_method": "llm",
                "provider": provider,
                "model": model,
            },
        )

    def _rule_based_plan(self, context: AIOSContext) -> AgentDecision:
        """Rule-based planning fallback (fast, no LLM needed)."""
        message = context.user_message.lower()
        actions = []

        # Image generation
        if any(w in message for w in ["image", "photo", "portrait", "picture", "generate"]):
            model = "flux-dev"
            if "fast" in message or "quick" in message or "draft" in message:
                model = "sdxl-turbo"

            actions.append(ProposedAction(
                tool="generate_image",
                parameters={
                    "prompt": context.user_message,
                    "model": model,
                    "talent_id": context.talent_id,
                },
                reasoning=f"Image generation requested. Model: {model}",
                confidence=0.8,
                estimated_cost_usd=0.003 if model == "flux-dev" else 0.0001,
                estimated_time_seconds=45 if model == "flux-dev" else 4,
            ))

        # Video generation
        if any(w in message for w in ["video", "clip", "animate", "motion"]):
            actions.append(ProposedAction(
                tool="generate_video",
                parameters={
                    "prompt": context.user_message,
                    "model": "wan-2.1-t2v",
                    "talent_id": context.talent_id,
                },
                reasoning="Video generation requested",
                confidence=0.75,
                estimated_cost_usd=0.05,
                estimated_time_seconds=120,
                requires_approval=True,
            ))

        # Training
        if any(w in message for w in ["train", "lora", "fine-tune", "learn"]):
            actions.append(ProposedAction(
                tool="train_lora",
                parameters={"talent_id": context.talent_id},
                reasoning="LoRA training requested",
                confidence=0.7,
                estimated_cost_usd=2.0,
                estimated_time_seconds=1200,
                requires_approval=True,
            ))

        # Voice
        if any(w in message for w in ["voice", "speak", "narrate", "tts"]):
            actions.append(ProposedAction(
                tool="generate_voice",
                parameters={"text": context.user_message},
                reasoning="Voice generation requested",
                confidence=0.75,
                estimated_cost_usd=0.01,
                estimated_time_seconds=10,
            ))

        # Publishing
        if any(w in message for w in ["publish", "post", "schedule", "instagram", "tiktok"]):
            actions.append(ProposedAction(
                tool="schedule_post",
                parameters={"content": context.user_message},
                reasoning="Publishing intent detected",
                confidence=0.7,
                requires_approval=True,
            ))

        if not actions:
            return AgentDecision(
                agent=self.name,
                summary="No specific actions needed — conversational response",
                reasoning="No actionable intent detected in message. Providing conversational response.",
                confidence=0.6,
                metadata={"planning_method": "rule_based", "intent": "chat"},
            )

        return AgentDecision(
            agent=self.name,
            summary=f"Plan: {len(actions)} action(s) — {', '.join(a.tool for a in actions)}",
            reasoning=f"Rule-based planning identified {len(actions)} steps",
            confidence=0.75,
            proposed_actions=actions,
            metadata={"planning_method": "rule_based"},
        )

    def _build_planning_prompt(self, context: AIOSContext) -> str:
        """Build the system prompt for LLM-powered planning."""
        from backend.aios.agent_dna import get_agent_dna

        base_dna = get_agent_dna("orunmila")
        prompt = base_dna + "\n\n" + """Given the user's request, create a brief execution plan.
List the steps clearly. If the user is just chatting, say "No actions needed — conversational."
"""
        if context.talent_name:
            prompt += f"\nActive Talent: {context.talent_name}"
        if context.talent_dna:
            prompt += f"\nCreative DNA: {context.talent_dna}"

        return prompt

    def _parse_plan_response(self, response: str, context: AIOSContext) -> list[ProposedAction]:
        """Parse LLM plan response into structured actions."""
        actions = []
        response_lower = response.lower()

        # Simple extraction: look for tool names in the response
        if "generate_image" in response_lower or "image" in response_lower:
            actions.append(ProposedAction(
                tool="generate_image",
                parameters={"prompt": context.user_message, "talent_id": context.talent_id},
                reasoning="LLM plan includes image generation",
                confidence=0.8,
            ))

        if "generate_video" in response_lower or "video" in response_lower:
            actions.append(ProposedAction(
                tool="generate_video",
                parameters={"prompt": context.user_message, "talent_id": context.talent_id},
                reasoning="LLM plan includes video generation",
                confidence=0.75,
                requires_approval=True,
            ))

        if "train_lora" in response_lower or "train" in response_lower:
            actions.append(ProposedAction(
                tool="train_lora",
                parameters={"talent_id": context.talent_id},
                reasoning="LLM plan includes training",
                confidence=0.7,
                requires_approval=True,
            ))

        if "no actions" in response_lower or "conversational" in response_lower:
            return []

        return actions
