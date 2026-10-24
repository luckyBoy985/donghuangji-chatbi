from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.audit import AuditLog
from backend.app.core.runtime import current_client_ip


def record_audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str = "",
    result: str = "success",
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        ip_address=current_client_ip() if ip_address is None else ip_address,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry
