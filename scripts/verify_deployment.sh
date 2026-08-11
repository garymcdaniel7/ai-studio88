#!/usr/bin/env bash
# =============================================================================
# Deployment Repeatability Verification Script
#
# Runs all build checks required for production deployment and records
# pass/fail with timestamp. Exit code 0 = all passed, 1 = failures.
#
# Validates: R109.1, R109.2, R109.3, R109.4, R109.5, R82.7, R82.8
#
# Usage:
#   ./scripts/verify_deployment.sh [--json] [--log-dir <dir>]
#
# Options:
#   --json       Output results as JSON to stdout
#   --log-dir    Directory to store verification logs (default: .deployment_logs)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Defaults
OUTPUT_JSON=false
LOG_DIR="${PROJECT_ROOT}/.deployment_logs"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) OUTPUT_JSON=true; shift ;;
        --log-dir) LOG_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_FILE="${LOG_DIR}/verification_${TIMESTAMP//[:.]/_}.json"
OVERALL_PASS=true
CHECKS=()

# =============================================================================
# Helper: record a check result
# =============================================================================
record_check() {
    local name="$1"
    local passed="$2"
    local message="$3"
    CHECKS+=("{\"check_name\":\"${name}\",\"passed\":${passed},\"message\":\"${message}\",\"checked_at\":\"${TIMESTAMP}\"}")
    if [ "$passed" = "false" ]; then
        OVERALL_PASS=false
    fi
}

# =============================================================================
# Check 1: Frontend Build (zero TypeScript/ESLint/Next.js errors)
# R109.4: All TypeScript errors, ESLint errors, and Next.js build errors
#          SHALL be zero for a clean deployment
# =============================================================================
echo "=== Check 1: Frontend Build ==="
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
if [ -d "${FRONTEND_DIR}" ] && [ -f "${FRONTEND_DIR}/package.json" ]; then
    cd "${FRONTEND_DIR}"
    if npm run build 2>&1 | tee /tmp/frontend_build_output.txt; then
        record_check "frontend_build" "true" "Frontend build succeeded with zero errors"
        echo "  PASS: Frontend build clean"
    else
        BUILD_ERR=$(tail -5 /tmp/frontend_build_output.txt | tr '\n' ' ' | sed 's/"/\\"/g')
        record_check "frontend_build" "false" "Frontend build failed: ${BUILD_ERR}"
        echo "  FAIL: Frontend build errors detected"
    fi
    cd "${PROJECT_ROOT}"
else
    record_check "frontend_build" "false" "Frontend directory or package.json not found"
    echo "  SKIP: Frontend directory not found"
fi

# =============================================================================
# Check 2: Backend Lint (ruff)
# =============================================================================
echo "=== Check 2: Backend Lint ==="
BACKEND_DIR="${PROJECT_ROOT}/backend"
if [ -d "${BACKEND_DIR}" ]; then
    cd "${PROJECT_ROOT}"
    if uv run ruff check backend/ 2>&1 | tee /tmp/backend_lint_output.txt; then
        record_check "backend_lint" "true" "Backend lint (ruff) passed with zero errors"
        echo "  PASS: Backend lint clean"
    else
        LINT_ERR=$(tail -3 /tmp/backend_lint_output.txt | tr '\n' ' ' | sed 's/"/\\"/g')
        record_check "backend_lint" "false" "Backend lint failed: ${LINT_ERR}"
        echo "  FAIL: Backend lint errors detected"
    fi
else
    record_check "backend_lint" "false" "Backend directory not found"
    echo "  SKIP: Backend directory not found"
fi

# =============================================================================
# Check 3: Backend Type Compilation (verify main module compiles)
# =============================================================================
echo "=== Check 3: Backend Compilation ==="
if [ -f "${BACKEND_DIR}/main.py" ]; then
    cd "${PROJECT_ROOT}"
    if uv run python -m py_compile backend/main.py 2>&1; then
        record_check "backend_compile" "true" "Backend main.py compiles without errors"
        echo "  PASS: Backend compilation clean"
    else
        record_check "backend_compile" "false" "Backend main.py compilation failed"
        echo "  FAIL: Backend compilation errors"
    fi
else
    record_check "backend_compile" "false" "backend/main.py not found"
    echo "  SKIP: backend/main.py not found"
fi

# =============================================================================
# Check 4: No suppressed build checks
# R109.4/R82.8: Deployment with ignored, disabled, or suppressed required
#               build errors SHALL NOT constitute clean production evidence
# =============================================================================
echo "=== Check 4: No Suppressed Build Checks ==="
SUPPRESSION_FOUND=false
SUPPRESSION_DETAILS=""

# Check for @ts-nocheck in TypeScript/TSX files (critical paths)
if [ -d "${FRONTEND_DIR}/src" ]; then
    TS_NOCHECK_COUNT=$(grep -r "// @ts-nocheck\|// @ts-ignore" "${FRONTEND_DIR}/src" --include="*.ts" --include="*.tsx" 2>/dev/null | wc -l | tr -d ' ')
    if [ "${TS_NOCHECK_COUNT}" -gt 0 ]; then
        SUPPRESSION_FOUND=true
        SUPPRESSION_DETAILS="${SUPPRESSION_DETAILS} ts-nocheck/ts-ignore: ${TS_NOCHECK_COUNT} occurrences;"
    fi
fi

# Check for eslint-disable in critical frontend paths
if [ -d "${FRONTEND_DIR}/src" ]; then
    ESLINT_DISABLE_COUNT=$(grep -r "eslint-disable-next-line\|eslint-disable " "${FRONTEND_DIR}/src/app" "${FRONTEND_DIR}/src/lib" 2>/dev/null | wc -l | tr -d ' ')
    if [ "${ESLINT_DISABLE_COUNT}" -gt 0 ]; then
        SUPPRESSION_FOUND=true
        SUPPRESSION_DETAILS="${SUPPRESSION_DETAILS} eslint-disable in critical paths: ${ESLINT_DISABLE_COUNT};"
    fi
fi

# Check for type: ignore in backend security modules
if [ -d "${BACKEND_DIR}/app/core" ]; then
    TYPE_IGNORE_COUNT=$(grep -r "# type: ignore" "${BACKEND_DIR}/app/core/security.py" "${BACKEND_DIR}/app/core/dependencies.py" 2>/dev/null | wc -l | tr -d ' ')
    if [ "${TYPE_IGNORE_COUNT}" -gt 0 ]; then
        SUPPRESSION_FOUND=true
        SUPPRESSION_DETAILS="${SUPPRESSION_DETAILS} type-ignore in security modules: ${TYPE_IGNORE_COUNT};"
    fi
fi

if [ "${SUPPRESSION_FOUND}" = "true" ]; then
    record_check "no_suppressed_checks" "false" "Suppressed checks found:${SUPPRESSION_DETAILS}"
    echo "  FAIL: Suppressed build checks detected"
else
    record_check "no_suppressed_checks" "true" "No suppressed or disabled build checks found"
    echo "  PASS: No suppressed build checks"
fi

# =============================================================================
# Write results
# =============================================================================
CHECKS_JSON=$(printf '%s,' "${CHECKS[@]}" | sed 's/,$//')

RESULT_JSON="{
  \"timestamp\": \"${TIMESTAMP}\",
  \"overall_passed\": ${OVERALL_PASS},
  \"checks\": [${CHECKS_JSON}],
  \"git_branch\": \"$(git -C "${PROJECT_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')\",
  \"git_sha\": \"$(git -C "${PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo 'unknown')\"
}"

echo "${RESULT_JSON}" > "${LOG_FILE}"

if [ "${OUTPUT_JSON}" = "true" ]; then
    echo "${RESULT_JSON}"
fi

echo ""
echo "=== Verification Complete ==="
echo "  Result: $([ "${OVERALL_PASS}" = "true" ] && echo "ALL PASSED" || echo "FAILURES DETECTED")"
echo "  Log: ${LOG_FILE}"

# Exit with appropriate code
if [ "${OVERALL_PASS}" = "true" ]; then
    exit 0
else
    exit 1
fi
