"""Application service layer — business logic orchestration.

Services handle business logic and orchestration between data access (repositories),
external providers, and the API layer (routers). No direct DB queries here — all
data access flows through the Supabase client or repository layer.

Conventions:
    - One service class per domain concept
    - Services receive dependencies via __init__ (constructor injection)
    - All public methods have type annotations and docstrings
    - Services validate org_id ownership on every mutation
"""
