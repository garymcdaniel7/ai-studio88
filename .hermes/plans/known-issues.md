# Known Pre-Existing Issues (not introduced by this session)

## Test-isolation collision (backend)
- **Symptom:** `pytest tests/unit/test_services/test_job_service.py tests/unit/test_repositories/test_job_repository.py -q` errors at setup with `TypeError: object MagicMock can't be used in 'await' expression`. Each file passes alone.
- **Root cause:** `tests/unit/test_services/test_job_service.py` does module-scope `sys.modules.setdefault("app.models", ...)` / `app.models.job` / `job_lease` / `talent` / `asset` to stub real SQLAlchemy models so it can import `app.services.job_service` against mocks. These `setdefault` calls permanently replace the real model modules for the whole pytest process. When `test_repositories/test_job_repository.py` is collected later, `app.repositories.job_repository` does `from app.models.job import Job` and gets the mock → non-awaitable MagicMock.
- **Proven pre-existing:** Reproduces on the committed baseline (my drift work didn't cause it; reverting my changes doesn't clear it). Verified order-independent.
- **Attempted fixes (all insufficient):** atexit restore, immediate restore after app imports, repo-conftest real-module re-import. The mock persists through module caching in a way these don't undo.
- **Status:** OPEN — pre-existing, does NOT block the product (all work's tests pass in isolation). Fix would require refactoring `test_job_service.py` to patch `app.models` via pytest fixtures/context-managers (monkeypatch.setitem inside an auto-restoring fixture) instead of module-scope setdefault.

## SQLAlchemy model class-collision collection errors (backend)
- `test_property_job_leasing.py`, `test_platform_operator_service.py`, `test_rights_case_service.py` error at COLLECTION with `SAWarning: declarative base already contains a class with the same class name and module name` (RightsCase, PlatformOperator). Pre-existing, unrelated to this session. Excluded from the green set.

## Video generation — no live ComfyUI engine on the GPU worker
- Worker's `VideoGenerationHandler` correctly fails fast with a clear error when ComfyUI is unreachable (fixed this session, commit ef620ce). BUT on the Vast worker, video jobs earlier hung because a video job spawned a subprocess (`wchan: do_wait`) that never returned — the worker blocked. Real video output requires ComfyUI actually installed + running on the GPU worker (COMFYUI_BASE_URL). Not yet provisioned.
