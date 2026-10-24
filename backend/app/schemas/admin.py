from pydantic import BaseModel, Field, field_validator


class AdminUserOut(BaseModel):
    id: str
    username: str
    display_name: str
    platform_role: str
    status: str
    must_change_password: bool
    created_at: str


class AdminPasswordReset(BaseModel):
    user_id: str
    temporary_password: str


class AdminUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    platform_role: str | None = Field(default=None, pattern=r"^(admin|user)$")
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class AdminTeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    owner_user_id: str = Field(min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("团队名称不能为空")
        return value


class AdminTeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class AdminTeamOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    owner_count: int
    member_count: int
    created_at: str


class AuditOut(BaseModel):
    id: str
    actor_user_id: str | None
    action: str
    resource_type: str
    resource_id: str
    result: str
    metadata: dict
    ip_address: str
    created_at: str
