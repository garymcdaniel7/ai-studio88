"""RLS Comprehensive Audit Script.

Queries the live Supabase database to produce a full RLS status report
for all public schema tables. Classifies findings by severity and outputs
a structured report suitable for remediation planning.

Usage:
    # Run against live Supabase (requires supabase CLI linked to project)
    python backend/scripts/rls_audit.py

    # Or with uv:
    uv run python backend/scripts/rls_audit.py

Validates: Requirements R6.1, R6.2, R6.5, R6.7, R2.4, R2.5
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


PROJECT_REF = "vipmjgglascthwoqqqji"

# Tables that are platform-operational (Category C) — no tenant dimension expected
CATEGORY_C_TABLES = {
    "_migration_ledger",
    "service_settings",
    "worker_connection_attempts",
    "worker_sessions",
    "workers",
}

# Tables that are system/shared (Category B) — readable by all
CATEGORY_B_TABLES = {
    "camera_presets",
    "lighting_presets",
    "pose_presets",
    "platform_packages",
    "scene_templates",
    "workflow_templates",
}

# Tables that are tenant-root (Category D)
CATEGORY_D_TABLES = {
    "organizations",
    "org_members",
}

# Tables containing sensitive user content (higher severity if unprotected)
SENSITIVE_TABLES = {
    "talent",
    "assets",
    "jobs",
    "brain_conversations",
    "brain_messages",
    "brain_memory",
    "brain_embeddings",
    "aios_sessions",
    "aios_messages",
    "aios_decisions",
    "aios_approvals",
    "training_datasets",
    "training_images",
    "training_jobs",
    "voice_profiles",
    "voice_samples",
    "voice_datasets",
    "publishing_accounts",
    "publishing_posts",
    "social_connections",
    "cost_records",
    "job_costs",
    "creative_dna",
    "workflow_dna",
}


class Severity(str, Enum):
    """Severity classification for RLS findings."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class TableRLSStatus:
    """RLS status for a single table."""

    table_name: str
    rls_enabled: bool
    policies: list[dict[str, Any]] = field(default_factory=list)
    has_org_id: bool = False
    org_id_nullable: bool = True
    category: str = "A"  # A, B, C, D
    severity: Severity = Severity.HIGH

    @property
    def has_policies(self) -> bool:
        return len(self.policies) > 0

    @property
    def has_ineffective_policies(self) -> bool:
        """Check if all policies use qual=true (allow everything)."""
        if not self.policies:
            return False
        return all(
            p.get("qual", "").strip().lower() == "true"
            or p.get("qual", "").strip() == "(true)"
            for p in self.policies
        )

    @property
    def has_effective_policies(self) -> bool:
        """Check if at least one policy does real filtering."""
        if not self.policies:
            return False
        return any(
            p.get("qual", "").strip().lower() != "true"
            and p.get("qual", "").strip() != "(true)"
            for p in self.policies
        )


def run_query_json(sql: str) -> list[dict[str, Any]]:
    """Run a SQL query against the linked Supabase project with JSON output."""
    cmd = [
        "supabase",
        "db",
        "query",
        "--linked",
        "--output-format",
        "json",
        sql,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"ERROR running query: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        raw = result.stdout.strip()

        # The output may contain non-JSON lines before the JSON array
        # (e.g., "Initialising login role...")
        # Find the start of the JSON array
        json_start = raw.find("[")
        if json_start == -1:
            # No JSON array found — might be empty result
            return []

        json_str = raw[json_start:]

        parsed = json.loads(json_str)
        if parsed is None:
            return []
        return parsed

    except subprocess.TimeoutExpired:
        print("ERROR: Query timed out after 60 seconds", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "ERROR: supabase CLI not found. Install with: brew install supabase/tap/supabase",
            file=sys.stderr,
        )
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON output: {e}", file=sys.stderr)
        print(f"Raw output (first 500 chars): {raw[:500]}", file=sys.stderr)
        return []


def get_all_tables() -> list[dict[str, Any]]:
    """Get all public schema tables with RLS status."""
    sql = """
        SELECT
            t.tablename AS table_name,
            t.rowsecurity AS rls_enabled
        FROM pg_tables t
        WHERE t.schemaname = 'public'
        ORDER BY t.tablename
    """
    return run_query_json(sql)


def get_all_policies() -> list[dict[str, Any]]:
    """Get all RLS policies for public schema tables."""
    sql = """
        SELECT
            p.tablename AS table_name,
            p.policyname AS policy_name,
            p.permissive AS permissive,
            p.roles::text AS roles,
            p.cmd AS cmd,
            p.qual::text AS qual,
            p.with_check::text AS with_check
        FROM pg_policies p
        WHERE p.schemaname = 'public'
        ORDER BY p.tablename, p.policyname
    """
    return run_query_json(sql)


def get_org_id_columns() -> list[dict[str, Any]]:
    """Check which tables have an org_id column and its nullability."""
    sql = """
        SELECT
            c.table_name,
            c.column_name,
            c.is_nullable
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.column_name = 'org_id'
        ORDER BY c.table_name
    """
    return run_query_json(sql)


def classify_table(table_name: str, has_org_id: bool, org_id_nullable: bool) -> str:
    """Classify a table into Category A, B, C, or D."""
    if table_name in CATEGORY_D_TABLES:
        return "D"
    if table_name in CATEGORY_C_TABLES:
        return "C"
    if table_name in CATEGORY_B_TABLES:
        return "B"
    return "A"


def determine_severity(
    table: TableRLSStatus,
) -> Severity:
    """Determine severity based on RLS status and table classification."""
    # Category C (platform-operational) and Category B (shared) are lower priority
    if table.category in ("C", "B"):
        return Severity.LOW

    # Category D (tenant-root) needs RLS but is lower priority since
    # these tables are managed by the auth system
    if table.category == "D":
        return Severity.MEDIUM

    # Category A tables:
    # RLS disabled entirely
    if not table.rls_enabled:
        return Severity.CRITICAL

    # RLS enabled but no policies AND contains sensitive data
    if not table.has_policies and table.table_name in SENSITIVE_TABLES:
        return Severity.CRITICAL

    # RLS enabled but no policies (other Category A tables)
    if not table.has_policies:
        return Severity.HIGH

    # Has policies but they're all qual=true (ineffective)
    if table.has_ineffective_policies:
        return Severity.MEDIUM

    # Has effective policies - good
    return Severity.LOW


def run_audit() -> list[TableRLSStatus]:
    """Run the full RLS audit and return classified results."""
    print("Fetching table list...", file=sys.stderr)
    tables = get_all_tables()
    print(f"  Found {len(tables)} tables", file=sys.stderr)

    print("Fetching RLS policies...", file=sys.stderr)
    policies = get_all_policies()
    print(f"  Found {len(policies)} policies", file=sys.stderr)

    print("Fetching org_id column info...", file=sys.stderr)
    org_id_info = get_org_id_columns()
    print(f"  Found {len(org_id_info)} tables with org_id", file=sys.stderr)

    # Build lookup maps
    policy_map: dict[str, list[dict[str, Any]]] = {}
    for p in policies:
        tname = p["table_name"]
        if tname not in policy_map:
            policy_map[tname] = []
        policy_map[tname].append(p)

    org_id_map: dict[str, dict[str, Any]] = {}
    for col in org_id_info:
        org_id_map[col["table_name"]] = col

    # Build results
    results: list[TableRLSStatus] = []
    for t in tables:
        table_name = t["table_name"]
        rls_enabled = t["rls_enabled"]

        has_org_id = table_name in org_id_map
        org_id_nullable = True
        if has_org_id:
            org_id_nullable = org_id_map[table_name]["is_nullable"] == "YES"

        category = classify_table(table_name, has_org_id, org_id_nullable)

        status = TableRLSStatus(
            table_name=table_name,
            rls_enabled=rls_enabled,
            policies=policy_map.get(table_name, []),
            has_org_id=has_org_id,
            org_id_nullable=org_id_nullable,
            category=category,
        )
        status.severity = determine_severity(status)
        results.append(status)

    return results


def format_report(results: list[TableRLSStatus]) -> str:
    """Format the audit results as a markdown report."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Group by severity
    by_severity: dict[Severity, list[TableRLSStatus]] = {
        Severity.CRITICAL: [],
        Severity.HIGH: [],
        Severity.MEDIUM: [],
        Severity.LOW: [],
    }
    for r in results:
        by_severity[r.severity].append(r)

    # Summary stats
    total = len(results)
    rls_enabled_count = sum(1 for r in results if r.rls_enabled)
    rls_disabled_count = total - rls_enabled_count
    has_policies_count = sum(1 for r in results if r.has_policies)
    no_policies_count = sum(1 for r in results if r.rls_enabled and not r.has_policies)
    ineffective_count = sum(1 for r in results if r.has_ineffective_policies)
    effective_count = sum(1 for r in results if r.has_effective_policies)
    has_org_id_count = sum(1 for r in results if r.has_org_id)
    no_org_id_count = total - has_org_id_count
    cat_a_count = sum(1 for r in results if r.category == "A")
    cat_a_no_org_id = sum(1 for r in results if r.category == "A" and not r.has_org_id)

    lines = [
        "# RLS Comprehensive Audit Results",
        "",
        f"**Date:** {now}",
        f"**Project:** {PROJECT_REF}",
        "**Method:** Automated query via `supabase db query --linked`",
        "**Validates:** Requirements R6.1, R6.2, R6.5, R6.7, R2.4, R2.5",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total tables (public schema) | {total} |",
        f"| RLS enabled | {rls_enabled_count} |",
        f"| RLS disabled | {rls_disabled_count} |",
        f"| Tables with at least one policy | {has_policies_count} |",
        f"| Tables with RLS but NO policies | {no_policies_count} |",
        f"| Tables with ineffective policies (qual=true) | {ineffective_count} |",
        f"| Tables with effective policies | {effective_count} |",
        f"| Tables with org_id column | {has_org_id_count} |",
        f"| Tables WITHOUT org_id column | {no_org_id_count} |",
        f"| Category A (tenant-scoped) tables | {cat_a_count} |",
        f"| Category A tables missing org_id | {cat_a_no_org_id} |",
        "",
        "### Severity Distribution",
        "",
        "| Severity | Count | Description |",
        "|----------|-------|-------------|",
        f"| CRITICAL | {len(by_severity[Severity.CRITICAL])} | RLS disabled or no policies + sensitive data |",
        f"| HIGH | {len(by_severity[Severity.HIGH])} | RLS enabled but no policies + user content |",
        f"| MEDIUM | {len(by_severity[Severity.MEDIUM])} | Ineffective qual=true policies |",
        f"| LOW | {len(by_severity[Severity.LOW])} | Platform-wide or already protected |",
        "",
        "---",
        "",
    ]

    # CRITICAL findings
    if by_severity[Severity.CRITICAL]:
        lines.extend([
            "## CRITICAL — Immediate Remediation Required",
            "",
            "These tables either have RLS completely disabled or have RLS enabled with",
            "no policies while containing sensitive user/tenant data.",
            "",
            "| Table | RLS Enabled | Policies | Has org_id | Issue |",
            "|-------|:-----------:|:--------:|:----------:|-------|",
        ])
        for r in sorted(by_severity[Severity.CRITICAL], key=lambda x: x.table_name):
            rls = "✅" if r.rls_enabled else "❌"
            pol = str(len(r.policies))
            org = "✅" if r.has_org_id else "❌"
            if not r.rls_enabled:
                issue = "RLS DISABLED — unprotected table"
            elif not r.has_policies:
                issue = "No policies — sensitive data exposed"
            else:
                issue = "Unknown critical issue"
            lines.append(f"| `{r.table_name}` | {rls} | {pol} | {org} | {issue} |")
        lines.extend(["", ""])

    # HIGH findings
    if by_severity[Severity.HIGH]:
        lines.extend([
            "## HIGH — RLS Enabled, No Policies (User Content)",
            "",
            "These Category A tables have RLS enabled but zero policies defined.",
            "Since the backend uses the service-role key (bypasses RLS), this provides",
            "no actual protection. If direct client access occurs, ALL rows are denied.",
            "",
            "| Table | Has org_id | Category | Remediation |",
            "|-------|:----------:|:--------:|-------------|",
        ])
        for r in sorted(by_severity[Severity.HIGH], key=lambda x: x.table_name):
            org = "✅" if r.has_org_id else "❌"
            if r.has_org_id and not r.org_id_nullable:
                remediation = "Add org_members-based RLS policy"
            elif r.has_org_id and r.org_id_nullable:
                remediation = "Backfill NULL org_id → NOT NULL, then add RLS policy"
            else:
                remediation = "Add org_id NOT NULL column first, then add RLS policy"
            lines.append(f"| `{r.table_name}` | {org} | {r.category} | {remediation} |")
        lines.extend(["", ""])

    # MEDIUM findings
    if by_severity[Severity.MEDIUM]:
        lines.extend([
            "## MEDIUM — Ineffective Policies (qual=true)",
            "",
            "These tables have RLS policies defined but the policies use `qual = true`",
            "which allows ALL access — providing zero actual tenant isolation.",
            "",
            "| Table | Policy Name | qual | with_check | Remediation |",
            "|-------|-------------|------|:----------:|-------------|",
        ])
        for r in sorted(by_severity[Severity.MEDIUM], key=lambda x: x.table_name):
            for p in r.policies:
                pname = p.get("policy_name", "—")
                qual = p.get("qual", "—")
                wc = p.get("with_check", "—") or "—"
                remediation = "Replace with org_members subquery USING + WITH CHECK"
                lines.append(
                    f"| `{r.table_name}` | {pname} | `{qual}` | `{wc}` | {remediation} |"
                )
        lines.extend(["", ""])

    # LOW findings
    if by_severity[Severity.LOW]:
        lines.extend([
            "## LOW — Platform-Wide or Already Protected",
            "",
            "These tables are either platform-operational (no tenant dimension),",
            "system/shared reference data, or already have effective RLS policies.",
            "",
            "| Table | Category | RLS | Policies | Notes |",
            "|-------|:--------:|:---:|:--------:|-------|",
        ])
        for r in sorted(by_severity[Severity.LOW], key=lambda x: x.table_name):
            rls = "✅" if r.rls_enabled else "—"
            pol = str(len(r.policies)) if r.policies else "0"
            if r.category == "B":
                notes = "System/shared — readable by all"
            elif r.category == "C":
                notes = "Platform-operational — no tenant dimension"
            elif r.has_effective_policies:
                notes = "Has effective tenant-scoping policy"
            else:
                notes = "Low priority"
            lines.append(f"| `{r.table_name}` | {r.category} | {rls} | {pol} | {notes} |")
        lines.extend(["", ""])

    # Remediation plan
    lines.extend([
        "---",
        "",
        "## Remediation Plan",
        "",
        "### Phase 1: Fix Critical Issues (Immediate)",
        "",
        "1. **Enable RLS on `workers` table** — add tenant policy or platform-admin-only policy",
        "2. **Add effective RLS policies to sensitive tables** that already have org_id:",
        "   - Replace `qual = true` with proper org_members subquery",
        "   - Template: `USING (org_id IN (SELECT om.org_id FROM org_members om "
        "WHERE om.user_id = auth.uid()))`",
        "",
        "### Phase 2: Add org_id Column (Prerequisite for Effective RLS)",
        "",
        "Before RLS policies can be effective, tables need `org_id NOT NULL`:",
        "",
        "1. **Create `organizations` and `org_members` tables** (prerequisite for all)",
        "2. **Add org_id to all 74 tables lacking it** (phased migration)",
        "3. **Backfill existing NULL org_id rows** → founder's org_id",
        "4. **Apply NOT NULL constraint** after backfill verification",
        "",
        "### Phase 3: Apply Production RLS Policies",
        "",
        "For each Category A table with org_id NOT NULL:",
        "",
        "```sql",
        "-- Template for tenant isolation RLS policy",
        "CREATE POLICY \"tenant_isolation_select\" ON <table>",
        "    FOR SELECT",
        "    USING (org_id IN (",
        "        SELECT om.org_id FROM public.org_members om",
        "        WHERE om.user_id = auth.uid()",
        "        AND om.status = 'active'",
        "    ));",
        "",
        "CREATE POLICY \"tenant_isolation_insert\" ON <table>",
        "    FOR INSERT",
        "    WITH CHECK (org_id IN (",
        "        SELECT om.org_id FROM public.org_members om",
        "        WHERE om.user_id = auth.uid()",
        "        AND om.status = 'active'",
        "    ));",
        "",
        "CREATE POLICY \"tenant_isolation_update\" ON <table>",
        "    FOR UPDATE",
        "    USING (org_id IN (",
        "        SELECT om.org_id FROM public.org_members om",
        "        WHERE om.user_id = auth.uid()",
        "        AND om.status = 'active'",
        "    ))",
        "    WITH CHECK (org_id IN (",
        "        SELECT om.org_id FROM public.org_members om",
        "        WHERE om.user_id = auth.uid()",
        "        AND om.status = 'active'",
        "    ));",
        "",
        "CREATE POLICY \"tenant_isolation_delete\" ON <table>",
        "    FOR DELETE",
        "    USING (org_id IN (",
        "        SELECT om.org_id FROM public.org_members om",
        "        WHERE om.user_id = auth.uid()",
        "        AND om.status = 'active'",
        "    ));",
        "",
        "-- Service-role bypass (backend uses service-role key)",
        "CREATE POLICY \"service_role_bypass\" ON <table>",
        "    FOR ALL",
        "    TO service_role",
        "    USING (true)",
        "    WITH CHECK (true);",
        "```",
        "",
        "### Phase 4: Verify and Automate",
        "",
        "1. **Write automated tests** — one per Category A table (R6.3)",
        "2. **Add CI check** — new migrations must include RLS policy (R6.5)",
        "3. **Document policies** in machine-readable format (R6.6)",
        "",
        "---",
        "",
        "## Tables Requiring org_id Column Addition (Before RLS Can Be Effective)",
        "",
        "The following Category A tables currently lack an `org_id` column entirely.",
        "RLS policies cannot provide tenant isolation until this column exists with NOT NULL.",
        "",
    ])

    # List tables needing org_id
    needs_org_id = [
        r for r in results if r.category == "A" and not r.has_org_id
    ]
    if needs_org_id:
        lines.append("| Table | Current State | Migration Required |")
        lines.append("|-------|--------------|-------------------|")
        for r in sorted(needs_org_id, key=lambda x: x.table_name):
            lines.append(
                f"| `{r.table_name}` | No org_id column | "
                "ADD COLUMN org_id UUID NOT NULL + backfill + index |"
            )
    lines.extend(["", ""])

    # Tables with nullable org_id
    nullable_org_id = [
        r for r in results if r.category == "A" and r.has_org_id and r.org_id_nullable
    ]
    if nullable_org_id:
        lines.extend([
            "## Tables With Nullable org_id (Backfill Required Before NOT NULL)",
            "",
            "These tables have the org_id column but it's nullable — existing NULL rows",
            "must be backfilled before the NOT NULL constraint can be applied.",
            "",
            "| Table | Current Policies | Backfill Strategy |",
            "|-------|-----------------|-------------------|",
        ])
        for r in sorted(nullable_org_id, key=lambda x: x.table_name):
            pol_count = len(r.policies)
            pol_str = f"{pol_count} (qual=true)" if r.has_ineffective_policies else str(pol_count)
            lines.append(
                f"| `{r.table_name}` | {pol_str} | "
                "Assign NULL rows to founder org_id |"
            )
        lines.extend(["", ""])

    # Footer
    lines.extend([
        "---",
        "",
        "## Verification Evidence",
        "",
        f"This report was generated on {now} via automated queries:",
        "",
        "```",
        "supabase db query --linked \"SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public'\"",
        "supabase db query --linked \"SELECT * FROM pg_policies WHERE schemaname='public'\"",
        "supabase db query --linked \"SELECT table_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema='public' AND column_name='org_id'\"",
        "```",
        "",
        "No schema modifications were made during this audit.",
    ])

    return "\n".join(lines)


def main() -> None:
    """Run the RLS audit and output results."""
    print("=" * 60, file=sys.stderr)
    print("RLS Comprehensive Audit", file=sys.stderr)
    print(f"Project: {PROJECT_REF}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    results = run_audit()

    report = format_report(results)

    # Output to stdout (can be redirected to file)
    print(report)

    # Summary to stderr
    print("\n" + "=" * 60, file=sys.stderr)
    print("AUDIT COMPLETE", file=sys.stderr)
    critical = sum(1 for r in results if r.severity == Severity.CRITICAL)
    high = sum(1 for r in results if r.severity == Severity.HIGH)
    medium = sum(1 for r in results if r.severity == Severity.MEDIUM)
    low = sum(1 for r in results if r.severity == Severity.LOW)
    print(f"  CRITICAL: {critical}", file=sys.stderr)
    print(f"  HIGH:     {high}", file=sys.stderr)
    print(f"  MEDIUM:   {medium}", file=sys.stderr)
    print(f"  LOW:      {low}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)


if __name__ == "__main__":
    main()
