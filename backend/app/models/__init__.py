"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogenerate and ``create_all`` see all tables.
"""

from app.models.alert import Alert
from app.models.behavior_profile import BehaviorProfile
from app.models.log_event import LogEvent
from app.models.user import User

__all__ = ["Alert", "BehaviorProfile", "LogEvent", "User"]
