"""Register every SQLAlchemy model when the package is imported.

API and Worker start from different entry points. Importing one model module in
isolation is not enough because its foreign keys may reference tables declared
by another module.
"""

from backend.app.models.audit import AuditLog, MigrationRecord
from backend.app.models.base import Base
from backend.app.models.entities import (
    Citation,
    Conversation,
    ConversationShare,
    Message,
    Report,
)
from backend.app.models.identity import (
    Invitation,
    LoginAttempt,
    Team,
    TeamMembership,
    User,
    UserSession,
)
from backend.app.models.ingestion import (
    DataChunk,
    DataDocument,
    DataSource,
    IngestJob,
)

__all__ = [
    "AuditLog",
    "Base",
    "Citation",
    "Conversation",
    "ConversationShare",
    "DataChunk",
    "DataDocument",
    "DataSource",
    "IngestJob",
    "Invitation",
    "LoginAttempt",
    "Message",
    "MigrationRecord",
    "Report",
    "Team",
    "TeamMembership",
    "User",
    "UserSession",
]
