"""Job handlers for the AI Studio worker.

Each handler in this package implements ``backend.worker.BaseHandler`` and is
registered in ``backend.worker.JOB_HANDLERS``. Handlers execute a job and
return a JSON-serializable output dict that is stored on the job record.
"""
