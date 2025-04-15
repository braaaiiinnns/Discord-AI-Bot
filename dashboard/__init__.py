# Dashboard package initialization
# This file forwards the imports from app.dashboard to maintain compatibility
from app.dashboard.dashboard import Dashboard

# Expose the Dashboard class
__all__ = ['Dashboard']