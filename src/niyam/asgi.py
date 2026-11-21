"""Module-level ASGI app for hosts that import one (Vercel, D69).

Containers run `uvicorn niyam.api:create_app --factory` instead, so importing this module is the
only thing that builds the live app at import time.
"""

from niyam.api import create_app

app = create_app()
