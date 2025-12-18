from .servers import router as servers_router
from .users import router as users_router
from .dashboard import router as dashboard_router
from .locations import router as locations_router
from .promocodes import router as promocodes_router
from .support import router as support_router
from .tutorials import router as tutorials_router
from .documentation import router as documentation_router
from .backup import router as backup_router

__all__ = ["servers_router", "users_router", "dashboard_router", "locations_router", "promocodes_router", "support_router", "tutorials_router", "documentation_router", "backup_router"]

