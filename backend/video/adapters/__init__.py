"""Video provider adapters — Story 143.

Each adapter implements CanonicalVideoProvider and isolates all
provider-specific logic. Shared orchestration never imports these
directly — they are loaded through the registry.
"""
