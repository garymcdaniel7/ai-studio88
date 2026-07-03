# Skill: Create GitHub Action

## Purpose

Create CI/CD workflows for AI Studio.

## PR lint + test workflow

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with: { version: "0.5.0" }
      - run: uv pip install --system ruff black
      - run: ruff check backend/ && black --check backend/

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv venv backend/.venv --python python3.12
      - run: uv pip install -e ".[dev]"
        working-directory: backend
      - run: pytest tests/unit/ -v
        working-directory: backend
        env:
          SECRET_KEY: "ci-test-secret-minimum-32-chars-long"
          SUPABASE_URL: "https://placeholder.supabase.co"
          SUPABASE_ANON_KEY: "placeholder"
          SUPABASE_SERVICE_ROLE_KEY: "placeholder"
          SUPABASE_JWT_SECRET: "placeholder"
          DATABASE_URL: "postgresql://user:pass@localhost/test"
          B2_KEY_ID: "placeholder"
          B2_APPLICATION_KEY: "placeholder"
          B2_BUCKET_NAME: "placeholder"
```

## Secrets to configure in GitHub

Repository → Settings → Secrets and variables → Actions:
- `STAGING_DATABASE_URL`, `STAGING_SUPABASE_URL`
- `STAGING_SUPABASE_SERVICE_ROLE_KEY`, `STAGING_SECRET_KEY`

## Branch protection for `main`

- Require 1 approved review
- Require CI checks to pass: `lint`, `test`, `docker`
- No direct pushes
