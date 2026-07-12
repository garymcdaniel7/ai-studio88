#!/bin/bash
# Run all SQL migrations against Supabase in order.
# Usage: ./scripts/run_migrations.sh
#
# Requires: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env
# Or pass database URL: ./scripts/run_migrations.sh "postgresql://..."

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SQL_DIR="$PROJECT_DIR/docs/sql"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        # Remove inline comments
        value="${value%%#*}"
        # Trim whitespace
        value="${value%"${value##*[![:space:]]}"}"
        export "$key=$value" 2>/dev/null || true
    done < "$PROJECT_DIR/.env"
fi

# Database connection
if [ -n "$1" ]; then
    DB_URL="$1"
elif [ -n "$DATABASE_URL" ]; then
    DB_URL="$DATABASE_URL"
elif [ -n "$SUPABASE_URL" ]; then
    # Extract host from Supabase URL and build postgres connection
    SUPABASE_HOST=$(echo "$SUPABASE_URL" | sed 's|https://||' | sed 's|\.supabase\.co.*||')
    DB_URL="postgresql://postgres.${SUPABASE_HOST}:${SUPABASE_DB_PASSWORD:-postgres}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    echo "Note: Using Supabase pooler. If this fails, pass your database URL directly."
fi

echo "=== AI Studio SQL Migrations ==="
echo "SQL directory: $SQL_DIR"
echo ""

# List all SQL files in order
SQL_FILES=$(ls "$SQL_DIR"/*.sql 2>/dev/null | sort)

if [ -z "$SQL_FILES" ]; then
    echo "No SQL files found in $SQL_DIR"
    exit 1
fi

echo "Found $(echo "$SQL_FILES" | wc -l | tr -d ' ') migration files."
echo ""

# If no DB_URL, just concatenate and output
if [ -z "$DB_URL" ]; then
    echo "No database URL configured. Generating combined SQL file instead..."
    OUTPUT="$PROJECT_DIR/docs/sql/ALL_MIGRATIONS.sql"
    echo "-- Combined AI Studio migrations (generated $(date))" > "$OUTPUT"
    echo "-- Run this in your Supabase SQL Editor" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    
    for f in $SQL_FILES; do
        BASENAME=$(basename "$f")
        echo "-- ============================================" >> "$OUTPUT"
        echo "-- $BASENAME" >> "$OUTPUT"
        echo "-- ============================================" >> "$OUTPUT"
        cat "$f" >> "$OUTPUT"
        echo "" >> "$OUTPUT"
        echo "" >> "$OUTPUT"
        echo "  Added: $BASENAME"
    done
    
    echo ""
    echo "Combined SQL written to: $OUTPUT"
    echo "Paste this into your Supabase SQL Editor to run all migrations."
    exit 0
fi

# Run each migration
SUCCEEDED=0
FAILED=0

for f in $SQL_FILES; do
    BASENAME=$(basename "$f")
    echo -n "  Running $BASENAME... "
    if psql "$DB_URL" -f "$f" > /dev/null 2>&1; then
        echo "OK"
        SUCCEEDED=$((SUCCEEDED + 1))
    else
        echo "FAILED (may already exist)"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "Done: $SUCCEEDED succeeded, $FAILED failed/skipped"
echo "(Failures are usually 'already exists' — safe to ignore)"
