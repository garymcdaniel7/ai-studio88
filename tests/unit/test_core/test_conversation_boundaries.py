"""Conversation/execution model boundary contract tests — Story 032.

Tests verify:
  - Each concept maps to exactly one canonical table
  - Compatibility tables reject new writes
  - Cross-reference rules are enforced
  - All 11 tables are classified
  - Presentation and execution domains don't collapse
  - Lifecycle dispositions are correct
  - Migration targets are valid canonical tables
  - Tenant ownership is marked for each table
"""

import pytest

from backend.conversation_models import (
    CONCEPT_TABLE_MAP,
    MODEL_REGISTRY,
    ModelDisposition,
    ModelDomain,
    get_canonical_table,
    get_disposition,
    get_domain,
    get_migration_target,
    is_writable,
    resolve_table,
    validate_cross_reference,
    validate_write_target,
)


# =============================================================================
# Registry Completeness
# =============================================================================


@pytest.mark.unit
class TestRegistryCompleteness:
    """Verify all known tables are classified."""

    EXPECTED_TABLES = {
        "brain_conversations", "brain_collections", "brain_embeddings",
        "brain_memory", "brain_plans", "brain_sessions", "brain_messages",
        "aios_sessions", "aios_messages", "aios_decisions",
        "aios_approvals", "aios_policies",
    }

    def test_all_tables_registered(self):
        """Every known Brain/AIOS table must be in the registry."""
        registered = set(MODEL_REGISTRY.keys())
        missing = self.EXPECTED_TABLES - registered
        assert not missing, f"Tables missing from registry: {missing}"

    def test_no_table_in_multiple_concepts(self):
        """Each table maps to exactly one concept."""
        concepts_seen = {}
        for table, info in MODEL_REGISTRY.items():
            concept = info["concept"]
            if concept in concepts_seen:
                pytest.fail(f"Concept '{concept}' claimed by both {concepts_seen[concept]} and {table}")
            concepts_seen[concept] = table

    def test_all_concepts_have_tables(self):
        """Every concept in the lookup map has a valid table."""
        for concept, table in CONCEPT_TABLE_MAP.items():
            assert table in MODEL_REGISTRY, f"Concept '{concept}' maps to unknown table '{table}'"


# =============================================================================
# Write Boundary Enforcement
# =============================================================================


@pytest.mark.unit
class TestWriteBoundaries:
    """Verify compatibility tables reject writes."""

    def test_brain_sessions_not_writable(self):
        """Legacy brain_sessions rejects new writes."""
        assert is_writable("brain_sessions") is False

    def test_brain_messages_not_writable(self):
        """Legacy brain_messages rejects new writes."""
        assert is_writable("brain_messages") is False

    def test_aios_sessions_writable(self):
        """Canonical aios_sessions accepts writes."""
        assert is_writable("aios_sessions") is True

    def test_brain_conversations_writable(self):
        """Canonical brain_conversations accepts writes."""
        assert is_writable("brain_conversations") is True

    def test_validate_write_target_blocks_legacy(self):
        """validate_write_target raises for compatibility tables."""
        with pytest.raises(ValueError, match="no new writes"):
            validate_write_target("brain_sessions")

    def test_validate_write_target_blocks_unknown(self):
        """validate_write_target raises for unknown tables."""
        with pytest.raises(ValueError, match="Unknown table"):
            validate_write_target("nonexistent_table")

    def test_validate_write_target_allows_canonical(self):
        """validate_write_target passes for canonical tables."""
        validate_write_target("aios_sessions")  # Should not raise
        validate_write_target("brain_conversations")  # Should not raise


# =============================================================================
# Disposition Classification
# =============================================================================


@pytest.mark.unit
class TestDispositions:
    """Verify correct lifecycle dispositions."""

    def test_canonical_tables(self):
        canonical = [t for t, i in MODEL_REGISTRY.items() if i["disposition"] == ModelDisposition.CANONICAL]
        assert "aios_sessions" in canonical
        assert "aios_messages" in canonical
        assert "brain_conversations" in canonical
        assert "brain_collections" in canonical
        assert "brain_memory" in canonical

    def test_compatibility_tables(self):
        compat = [t for t, i in MODEL_REGISTRY.items() if i["disposition"] == ModelDisposition.COMPATIBILITY]
        assert "brain_sessions" in compat
        assert "brain_messages" in compat
        assert len(compat) == 2  # Only these two are legacy


# =============================================================================
# Domain Separation
# =============================================================================


@pytest.mark.unit
class TestDomainSeparation:
    """Verify presentation and execution don't collapse."""

    def test_presentation_tables(self):
        presentation = [t for t, i in MODEL_REGISTRY.items() if i["domain"] == ModelDomain.PRESENTATION]
        assert "brain_conversations" in presentation
        assert "brain_collections" in presentation
        # Execution tables must NOT be in presentation
        assert "aios_sessions" not in presentation
        assert "aios_messages" not in presentation

    def test_execution_tables(self):
        execution = [t for t, i in MODEL_REGISTRY.items() if i["domain"] == ModelDomain.EXECUTION]
        assert "aios_sessions" in execution
        assert "aios_messages" in execution
        assert "aios_decisions" in execution
        assert "brain_plans" in execution
        # Presentation tables must NOT be in execution
        assert "brain_conversations" not in execution

    def test_governance_tables(self):
        governance = [t for t, i in MODEL_REGISTRY.items() if i["domain"] == ModelDomain.GOVERNANCE]
        assert "aios_approvals" in governance
        assert "aios_policies" in governance

    def test_memory_tables(self):
        memory = [t for t, i in MODEL_REGISTRY.items() if i["domain"] == ModelDomain.MEMORY]
        assert "brain_memory" in memory
        assert "brain_embeddings" in memory


# =============================================================================
# Migration Targets
# =============================================================================


@pytest.mark.unit
class TestMigrationTargets:
    """Verify migration targets point to canonical tables."""

    def test_brain_sessions_migrates_to_aios_sessions(self):
        target = get_migration_target("brain_sessions")
        assert target == "aios_sessions"

    def test_brain_messages_migrates_to_aios_messages(self):
        target = get_migration_target("brain_messages")
        assert target == "aios_messages"

    def test_migration_targets_are_canonical(self):
        """Every migration target must be a canonical table."""
        for table, info in MODEL_REGISTRY.items():
            target = info.get("migration_target")
            if target:
                target_info = MODEL_REGISTRY.get(target)
                assert target_info is not None, f"{table} migrates to unknown table {target}"
                assert target_info["disposition"] == ModelDisposition.CANONICAL


# =============================================================================
# Concept Resolution
# =============================================================================


@pytest.mark.unit
class TestConceptResolution:
    """Verify concept → table resolution works correctly."""

    def test_user_conversation_resolves(self):
        assert resolve_table("user_conversation") == "brain_conversations"

    def test_execution_session_resolves(self):
        assert resolve_table("execution_session") == "aios_sessions"

    def test_execution_message_resolves(self):
        assert resolve_table("execution_message") == "aios_messages"

    def test_ai_decision_resolves(self):
        assert resolve_table("ai_decision") == "aios_decisions"

    def test_approval_resolves(self):
        assert resolve_table("approval") == "aios_approvals"

    def test_long_term_memory_resolves(self):
        assert resolve_table("long_term_memory") == "brain_memory"

    def test_unknown_concept_raises(self):
        with pytest.raises(ValueError, match="Unknown concept"):
            resolve_table("nonexistent_concept")


# =============================================================================
# Tenant Ownership Coverage
# =============================================================================


@pytest.mark.unit
class TestTenantOwnership:
    """Verify tenant scoping is marked for each table."""

    def test_all_canonical_tables_are_tenant_scoped(self):
        """Every canonical table must be tenant-scoped."""
        for table, info in MODEL_REGISTRY.items():
            if info["disposition"] == ModelDisposition.CANONICAL:
                assert info["tenant_scoped"] is True, (
                    f"Canonical table '{table}' must be tenant-scoped"
                )

    def test_compatibility_tables_marked_unverified(self):
        """Compatibility tables should have explicit tenant_scoped flag."""
        for table, info in MODEL_REGISTRY.items():
            if info["disposition"] == ModelDisposition.COMPATIBILITY:
                # These are marked False because org_id is not reliably enforced
                assert "tenant_scoped" in info


# =============================================================================
# Architecture Document Exists
# =============================================================================


@pytest.mark.unit
class TestDocumentationExists:
    """Verify the architecture document was created."""

    def test_boundary_document_exists(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        doc_path = os.path.join(repo_root, "docs", "architecture", "CONVERSATION_MODEL_BOUNDARIES.md")
        assert os.path.exists(doc_path)

    def test_document_has_canonical_map(self):
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        doc_path = os.path.join(repo_root, "docs", "architecture", "CONVERSATION_MODEL_BOUNDARIES.md")
        with open(doc_path) as f:
            content = f.read()
        assert "Canonical Entity Map" in content
        assert "CANONICAL" in content
        assert "COMPATIBILITY" in content
        assert "brain_conversations" in content
        assert "aios_sessions" in content
