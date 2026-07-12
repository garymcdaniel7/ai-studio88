"""AIOS Execution Layer — executes approved actions from the Agent Council.

When Orunmila proposes an action and governance approves it,
this layer actually does the work:
- Generate images/videos via Worker API or ComfyUI
- Train LoRAs via the training pipeline
- Create/update talent records
- Schedule publishing
- Search and retrieve from knowledge graph

Each tool has an executor function that bridges
AIOS → existing backend services.
"""
