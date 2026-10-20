"""Service-layer glue for the FirstShift backend.

Thin wrappers that compose the pure core (app/core) with persistence:
no business logic lives here, only the dispatch-and-persist path shared by
the webhook handler and scripted flows.
"""
