#!/bin/bash
# Run the AIOS scale test on the Vast worker with Supabase env from .env
cd /root/backend || exit 1
export SUPABASE_URL="$(grep '^SUPABASE_URL=' .env | cut -d= -f2)"
export SUPABASE_SERVICE_ROLE_KEY="$(grep '^SUPABASE_SERVICE_ROLE_KEY=' .env | cut -d= -f2)"
python3 scripts/aios_scale_test.py --jobs 6 --watch 90
