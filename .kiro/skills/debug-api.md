# Skill: Debug API Issues

## Diagnostic steps

### 1. Check API is running
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 2. Authentication issues
```bash
# Decode JWT payload (no verification)
python3 -c "
import base64, json, sys
token = sys.argv[1].split('.')[1]
padded = token + '=' * (4 - len(token) % 4)
print(json.dumps(json.loads(base64.urlsafe_b64decode(padded)), indent=2))
" YOUR_JWT_HERE
# Check: exp not in the past, sub present, SUPABASE_JWT_SECRET matches
```

### 3. Database issues
```bash
# Check migrations
cd backend && alembic current && alembic history
# Test connection
python3 -c "
import asyncio
from app.db.session import get_session_factory
from sqlalchemy import text
async def test():
    async with get_session_factory()() as s:
        print(await s.scalar(text('SELECT version()')))
asyncio.run(test())
"
```

### 4. Celery/Redis issues
```bash
redis-cli ping                                    # PONG
celery -A app.workers.celery_app inspect ping     # worker alive?
celery -A app.workers.celery_app inspect reserved # queue depth
```

## Common errors

| Error | Likely cause | Fix |
|---|---|---|
| 401 | Missing/expired JWT | Re-auth, check SUPABASE_JWT_SECRET |
| 403 | Wrong org_id | Check JWT org claim |
| 422 | Bad request body | Check `detail[].loc` for field name |
| 500 | Unhandled exception | Check logs for traceback |
| 503 | DB not ready | Run `supabase start`, check DATABASE_URL |
| `:8000` refused | API not running | `uvicorn app.main:app --reload` |
| `:6379` refused | Redis not running | `docker compose up -d redis` |
