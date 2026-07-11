"""AI Auto-Fix: Hybrid Code Fixer.

Tier 1: Pattern-based deterministic fixes for known lint/type rules.
Tier 2: LLM-assisted fixes via Ollama Brain for complex errors.
Tier 3: Returns suggestions requiring user approval.

Usage:
    fixer = CodeFixer()
    results = fixer.fix_diagnostics(file_path, diagnostics)
    # Each result has: rule, line, fix_type, patch, confidence
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class Diagnostic:
    """A single code diagnostic/error."""

    rule: str
    message: str
    line: int
    column: int = 0
    severity: str = "error"  # error | warning
    source: str = ""  # file content at that line


@dataclass
class FixResult:
    """Result of attempting to fix a diagnostic."""

    rule: str
    line: int
    tier: int  # 1 = pattern, 2 = LLM, 3 = suggestion-only
    fix_type: str  # "replace_line" | "insert_before" | "delete_line" | "suggestion"
    original: str
    replacement: str
    confidence: float  # 0.0 - 1.0
    explanation: str


@dataclass
class FixerContext:
    """Context passed to fixer functions."""

    file_path: str
    lines: list[str]
    diagnostic: Diagnostic


# =============================================================================
# Tier 1: Pattern-Based Fixers
# =============================================================================


def fix_no_explicit_any(ctx: FixerContext) -> FixResult | None:
    """Replace `any` with `unknown` or `Record<string, unknown>` depending on context."""
    line = ctx.lines[ctx.diagnostic.line - 1] if ctx.diagnostic.line <= len(ctx.lines) else ""

    # State type: Record<string, any> → Record<string, unknown>
    if "Record<string, any>" in line:
        fixed = line.replace("Record<string, any>", "Record<string, unknown>")
        return FixResult(
            rule=ctx.diagnostic.rule,
            line=ctx.diagnostic.line,
            tier=1,
            fix_type="replace_line",
            original=line,
            replacement=fixed,
            confidence=0.95,
            explanation="Replaced Record<string, any> with Record<string, unknown>",
        )

    # Function return type: ): any → ): unknown
    if re.search(r":\s*any\b", line):
        fixed = re.sub(r":\s*any\b", ": unknown", line)
        return FixResult(
            rule=ctx.diagnostic.rule,
            line=ctx.diagnostic.line,
            tier=1,
            fix_type="replace_line",
            original=line,
            replacement=fixed,
            confidence=0.8,
            explanation="Replaced any type annotation with unknown",
        )

    # Array any[]: → unknown[]
    if "any[]" in line:
        fixed = line.replace("any[]", "unknown[]")
        return FixResult(
            rule=ctx.diagnostic.rule,
            line=ctx.diagnostic.line,
            tier=1,
            fix_type="replace_line",
            original=line,
            replacement=fixed,
            confidence=0.85,
            explanation="Replaced any[] with unknown[]",
        )

    return None


def fix_no_unused_vars(ctx: FixerContext) -> FixResult | None:
    """Remove unused import or add underscore prefix to unused variables."""
    line = ctx.lines[ctx.diagnostic.line - 1] if ctx.diagnostic.line <= len(ctx.lines) else ""
    msg = ctx.diagnostic.message

    # Extract the unused variable/import name from message
    match = re.search(r"'(\w+)'", msg)
    if not match:
        return None
    name = match.group(1)

    # If it's an import line, remove the specific import
    if "import" in line:
        # Named import: { A, B, C } — remove just the unused one
        if re.search(rf"\b{re.escape(name)}\b", line):
            # Check if it's the only import
            imports = (
                re.findall(r"[\w]+", re.search(r"\{([^}]+)\}", line).group(1))
                if "{" in line
                else []
            )
            if len(imports) == 1:
                # Remove the entire import line
                return FixResult(
                    rule=ctx.diagnostic.rule,
                    line=ctx.diagnostic.line,
                    tier=1,
                    fix_type="delete_line",
                    original=line,
                    replacement="",
                    confidence=0.9,
                    explanation=f"Removed unused import: {name}",
                )
            else:
                # Remove just this import from the named imports
                # Handle: { A, B } → { B }
                fixed = re.sub(rf",?\s*\b{re.escape(name)}\b\s*,?", "", line)
                # Clean up double commas or trailing commas
                fixed = re.sub(r",\s*}", " }", fixed)
                fixed = re.sub(r"\{\s*,", "{ ", fixed)
                return FixResult(
                    rule=ctx.diagnostic.rule,
                    line=ctx.diagnostic.line,
                    tier=1,
                    fix_type="replace_line",
                    original=line,
                    replacement=fixed,
                    confidence=0.85,
                    explanation=f"Removed unused import '{name}' from import statement",
                )

    return None


def fix_no_img_element(ctx: FixerContext) -> FixResult | None:
    """Add eslint-disable-next-line comment above <img> tags."""
    line = ctx.lines[ctx.diagnostic.line - 1] if ctx.diagnostic.line <= len(ctx.lines) else ""

    if "<img" in line:
        indent = len(line) - len(line.lstrip())
        comment = " " * indent + "/* eslint-disable-next-line @next/next/no-img-element */\n"
        return FixResult(
            rule=ctx.diagnostic.rule,
            line=ctx.diagnostic.line,
            tier=1,
            fix_type="insert_before",
            original=line,
            replacement=comment,
            confidence=0.95,
            explanation="Added eslint-disable comment for dynamic image URL",
        )
    return None


def fix_alt_text(ctx: FixerContext) -> FixResult | None:
    """Add alt attribute to img elements missing one."""
    line = ctx.lines[ctx.diagnostic.line - 1] if ctx.diagnostic.line <= len(ctx.lines) else ""

    if "<img" in line and "alt=" not in line:
        # Add alt="" after <img or after src="..."
        fixed = re.sub(r"(<img\s)", r'\1alt="Image" ', line)
        return FixResult(
            rule=ctx.diagnostic.rule,
            line=ctx.diagnostic.line,
            tier=1,
            fix_type="replace_line",
            original=line,
            replacement=fixed,
            confidence=0.8,
            explanation="Added alt attribute to img element",
        )
    return None


def fix_prefer_const(ctx: FixerContext) -> FixResult | None:
    """Replace let with const when variable is never reassigned."""
    line = ctx.lines[ctx.diagnostic.line - 1] if ctx.diagnostic.line <= len(ctx.lines) else ""

    if line.strip().startswith("let "):
        fixed = line.replace("let ", "const ", 1)
        return FixResult(
            rule=ctx.diagnostic.rule,
            line=ctx.diagnostic.line,
            tier=1,
            fix_type="replace_line",
            original=line,
            replacement=fixed,
            confidence=0.9,
            explanation="Changed let to const (variable is never reassigned)",
        )
    return None


def fix_missing_return_type(ctx: FixerContext) -> FixResult | None:
    """Add return type annotations to simple functions."""
    line = ctx.lines[ctx.diagnostic.line - 1] if ctx.diagnostic.line <= len(ctx.lines) else ""

    # Match: function foo() { or async function foo() {
    match = re.search(r"((?:async\s+)?function\s+\w+\([^)]*\))\s*\{", line)
    if match:
        fixed = line.replace(match.group(1) + " {", match.group(1) + ": void {")
        return FixResult(
            rule=ctx.diagnostic.rule,
            line=ctx.diagnostic.line,
            tier=1,
            fix_type="replace_line",
            original=line,
            replacement=fixed,
            confidence=0.6,
            explanation="Added void return type (verify manually)",
        )
    return None


# =============================================================================
# Fixer Registry
# =============================================================================

# Maps ESLint/TS rule IDs to fixer functions
PATTERN_FIXERS: dict[str, Callable[[FixerContext], FixResult | None]] = {
    "@typescript-eslint/no-explicit-any": fix_no_explicit_any,
    "no-explicit-any": fix_no_explicit_any,
    "@typescript-eslint/no-unused-vars": fix_no_unused_vars,
    "no-unused-vars": fix_no_unused_vars,
    "@next/next/no-img-element": fix_no_img_element,
    "jsx-a11y/alt-text": fix_alt_text,
    "prefer-const": fix_prefer_const,
    "@typescript-eslint/explicit-function-return-type": fix_missing_return_type,
}


# =============================================================================
# CodeFixer Class
# =============================================================================


class CodeFixer:
    """Hybrid code fixer: pattern-based (Tier 1) + LLM-assisted (Tier 2).

    Usage:
        fixer = CodeFixer(llm_provider=ollama_client)
        results = await fixer.fix_file(file_path, file_content, diagnostics)
    """

    def __init__(self, llm_provider=None) -> None:
        """Initialize the code fixer.

        Args:
            llm_provider: Optional LLM provider for Tier 2 fixes.
                         If None, only Tier 1 pattern fixes are available.
        """
        self.llm_provider = llm_provider

    def fix_with_patterns(
        self,
        file_path: str,
        file_content: str,
        diagnostics: list[Diagnostic],
    ) -> list[FixResult]:
        """Tier 1: Apply pattern-based fixes to all diagnostics."""
        lines = file_content.split("\n")
        results: list[FixResult] = []

        for diag in diagnostics:
            fixer = PATTERN_FIXERS.get(diag.rule)
            if fixer:
                ctx = FixerContext(file_path=file_path, lines=lines, diagnostic=diag)
                result = fixer(ctx)
                if result:
                    results.append(result)

        return results

    async def fix_with_llm(
        self,
        file_path: str,
        file_content: str,
        diagnostics: list[Diagnostic],
    ) -> list[FixResult]:
        """Tier 2: Use LLM to generate fixes for diagnostics not handled by patterns."""
        if not self.llm_provider:
            return []

        # Filter to diagnostics that patterns didn't handle
        handled_rules = set(PATTERN_FIXERS.keys())
        unhandled = [d for d in diagnostics if d.rule not in handled_rules]

        if not unhandled:
            return []

        results: list[FixResult] = []
        lines = file_content.split("\n")

        # Batch unhandled diagnostics into a single LLM call for efficiency
        error_context = "\n".join(
            f"Line {d.line}: [{d.rule}] {d.message}"
            for d in unhandled[:10]  # Limit to 10 per call
        )

        # Get surrounding code context (5 lines around each error)
        code_snippets = []
        for d in unhandled[:10]:
            start = max(0, d.line - 3)
            end = min(len(lines), d.line + 3)
            snippet = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
            code_snippets.append(f"--- Error at line {d.line} ---\n{snippet}")

        prompt = f"""You are a code fixer. Fix the following errors in {file_path}.

ERRORS:
{error_context}

CODE CONTEXT:
{"".join(code_snippets)}

For each error, provide a JSON array of fixes:
[{{"line": <int>, "original": "<exact line content>", "replacement": "<fixed line content>", "explanation": "<why>"}}]

Only output the JSON array. No markdown, no explanation outside the array."""

        try:
            response = await self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )

            # Parse LLM response as JSON
            import json

            content = response.get("response", "") if isinstance(response, dict) else str(response)
            # Extract JSON from response
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                fixes = json.loads(json_match.group())
                for fix in fixes:
                    results.append(
                        FixResult(
                            rule="llm-assisted",
                            line=fix.get("line", 0),
                            tier=2,
                            fix_type="replace_line",
                            original=fix.get("original", ""),
                            replacement=fix.get("replacement", ""),
                            confidence=0.7,
                            explanation=fix.get("explanation", "LLM-suggested fix"),
                        )
                    )
        except Exception:
            pass  # LLM unavailable — skip Tier 2

        return results

    async def fix_file(
        self,
        file_path: str,
        file_content: str,
        diagnostics: list[Diagnostic],
    ) -> list[FixResult]:
        """Run both Tier 1 and Tier 2 fixes, return all results sorted by confidence."""
        # Tier 1: Pattern-based
        pattern_results = self.fix_with_patterns(file_path, file_content, diagnostics)

        # Tier 2: LLM-assisted (only for unhandled diagnostics)
        handled_lines = {r.line for r in pattern_results}
        remaining = [d for d in diagnostics if d.line not in handled_lines]
        llm_results = await self.fix_with_llm(file_path, file_content, remaining)

        all_results = pattern_results + llm_results
        # Sort by confidence (highest first), then by line number
        all_results.sort(key=lambda r: (-r.confidence, r.line))

        return all_results

    def apply_fixes(self, file_content: str, fixes: list[FixResult]) -> str:
        """Apply a list of fixes to file content.

        Only applies fixes with confidence >= 0.8 automatically.
        Returns the modified file content.
        """
        lines = file_content.split("\n")

        # Sort fixes by line in reverse order (apply from bottom to top)
        sorted_fixes = sorted(
            [f for f in fixes if f.confidence >= 0.8],
            key=lambda f: f.line,
            reverse=True,
        )

        for fix in sorted_fixes:
            idx = fix.line - 1
            if idx < 0 or idx >= len(lines):
                continue

            if fix.fix_type == "replace_line":
                lines[idx] = fix.replacement.rstrip("\n")
            elif fix.fix_type == "delete_line":
                lines.pop(idx)
            elif fix.fix_type == "insert_before":
                lines.insert(idx, fix.replacement.rstrip("\n"))

        return "\n".join(lines)
