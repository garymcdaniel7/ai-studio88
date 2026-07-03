"""Execution Planner — breaks user requests into executable task plans.

Analyzes natural language requests, identifies required modules,
builds an ordered execution plan, and estimates resources.
"""
from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from typing import Any

from backend.brain.registry import find_modules_for_intent, MODULES


@dataclass
class Task:
    """A single task in an execution plan."""
    id: str = ""
    name: str = ""
    module: str = ""
    action: str = ""
    parameters: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    estimated_seconds: int = 30
    metadata: dict = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """A complete plan for fulfilling a user request."""
    id: str = ""
    request: str = ""
    tasks: list[Task] = field(default_factory=list)
    reasoning: str = ""
    estimated_total_seconds: int = 0
    estimated_cost: str = ""
    confidence: float = 0.8
    modules_involved: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def create_plan(user_request: str, context: dict | None = None) -> ExecutionPlan:
    """Create an execution plan from a natural language request.

    Analyzes the request, identifies required modules, and builds
    an ordered task list with dependencies.
    """
    ctx = context or {}
    request_lower = user_request.lower()
    plan_id = uuid.uuid4().hex[:12]
    tasks = []
    reasoning_parts = []
    modules_used = set()

    # Detect intent and build tasks
    task_id = lambda: uuid.uuid4().hex[:8]

    # Always start with planning/intelligence
    plan_task_id = task_id()
    tasks.append(Task(
        id=plan_task_id, name="Analyze Creative Intent",
        module="creative_session", action="plan",
        parameters={"idea": user_request},
        estimated_seconds=5,
    ))
    modules_used.add("Creative Session")
    reasoning_parts.append("Starting with creative analysis")

    # Story/narrative detection
    if any(w in request_lower for w in ["series", "episode", "film", "movie", "story", "scene"]):
        story_id = task_id()
        tasks.append(Task(
            id=story_id, name="Create Story Structure",
            module="story_engine", action="create",
            parameters={"description": user_request},
            depends_on=[plan_task_id],
            estimated_seconds=10,
        ))
        modules_used.add("Story Engine")
        reasoning_parts.append("Narrative content → Story Engine")

    # Image generation detection
    if any(w in request_lower for w in ["create", "generate", "photo", "portrait", "image", "luxury", "editorial"]):
        gen_id = task_id()
        tasks.append(Task(
            id=gen_id, name="Generate Visual Content",
            module="generation_engine", action="generate",
            parameters={"prompt": user_request},
            depends_on=[plan_task_id],
            estimated_seconds=30,
        ))
        modules_used.add("Generation Engine")
        reasoning_parts.append("Visual content detected → Generation Engine")

    # Video detection
    if any(w in request_lower for w in ["reel", "video", "tiktok", "short", "trailer", "commercial", "clip"]):
        vid_id = task_id()
        tasks.append(Task(
            id=vid_id, name="Create Video Production",
            module="video_studio", action="create",
            parameters={"description": user_request},
            depends_on=[plan_task_id],
            estimated_seconds=60,
        ))
        modules_used.add("Video Studio")
        reasoning_parts.append("Video content → Video Studio")

    # Voice/audio detection
    if any(w in request_lower for w in ["voice", "narration", "dialogue", "speak", "song", "music"]):
        voice_id = task_id()
        tasks.append(Task(
            id=voice_id, name="Generate Audio",
            module="voice_studio", action="generate",
            parameters={"text": user_request},
            depends_on=[plan_task_id],
            estimated_seconds=20,
        ))
        modules_used.add("Voice Studio")
        reasoning_parts.append("Audio content → Voice Studio")

    # Publishing detection
    if any(w in request_lower for w in ["publish", "post", "schedule", "instagram", "tiktok", "youtube"]):
        pub_id = task_id()
        tasks.append(Task(
            id=pub_id, name="Prepare for Publishing",
            module="publishing_engine", action="schedule",
            parameters={"platforms": ["instagram"]},
            depends_on=[t.id for t in tasks[1:]],  # After all content tasks
            estimated_seconds=10,
        ))
        modules_used.add("Publishing Engine")
        reasoning_parts.append("Publishing intent → Publishing Engine")

    # Campaign detection
    if any(w in request_lower for w in ["campaign", "brand", "launch"]):
        camp_id = task_id()
        tasks.append(Task(
            id=camp_id, name="Create Campaign",
            module="creator_os", action="campaign",
            parameters={"name": user_request[:50]},
            depends_on=[plan_task_id],
            estimated_seconds=5,
        ))
        modules_used.add("Creator OS")
        reasoning_parts.append("Campaign intent → Creator OS")

    # If nothing specific matched, default to generation
    if len(tasks) == 1:
        tasks.append(Task(
            id=task_id(), name="Generate Content",
            module="generation_engine", action="generate",
            parameters={"prompt": user_request},
            depends_on=[plan_task_id],
            estimated_seconds=30,
        ))
        modules_used.add("Generation Engine")
        reasoning_parts.append("General creative request → Generation")

    total_seconds = sum(t.estimated_seconds for t in tasks)

    return ExecutionPlan(
        id=plan_id,
        request=user_request,
        tasks=tasks,
        reasoning=" → ".join(reasoning_parts),
        estimated_total_seconds=total_seconds,
        estimated_cost=f"~${len(tasks) * 0.02:.2f}",
        confidence=0.8 if len(modules_used) > 1 else 0.7,
        modules_involved=list(modules_used),
    )
