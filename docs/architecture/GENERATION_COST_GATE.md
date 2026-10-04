# Generation Dispatch Cost Gate

Group 16.3 bridges the legacy synchronous `GenerationEngine` path rather than retiring it. The canonical entry point remains `POST /api/v1/generation/run`; governed action commands may also dispatch image generation. Both call `GenerationEngine.generate_and_register()`, which now uses the same `backend.generation_cost_gate.execute_with_cost_gate()` boundary as `Worker._process_job()`.

The boundary requires trusted `org_id` and `job_id`, reserves the server-side estimate before provider execution, finalizes after provider execution plus B2 upload and asset registration, and releases an active reservation on provider, timeout, scan, storage, or database failure. `GenerationEngine.generate()` retains its existing `finally` GPU-status cleanup and provider-specific timeout behavior.

The API derives organization ownership from the authenticated user and overwrites request context with that value. Client-supplied organization selectors are never used for cost, storage, jobs, or assets. Generation metadata and the immutable storage key retain organization, job, workflow, model, model version, provider, and cost provenance. Delivery URLs still come from the signed/CDN storage boundary; raw provider URLs and exception details are not returned to clients.
