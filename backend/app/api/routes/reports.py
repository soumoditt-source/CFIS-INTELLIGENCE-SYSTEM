"""AegisCX API Routes — stub files for reports and admin using shared module."""
from app.api.routes.reports_admin import router as reports_router, admin as admin_router

# Expose for main.py import
router = reports_router
