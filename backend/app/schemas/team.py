from pydantic import BaseModel, Field


class TeamOut(BaseModel):
    id: str
    name: str
    description: str
    role: str
    member_count: int


class TeamMemberOut(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: str
    created_at: str


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern=r"^(owner|admin|member)$")


class InvitationCreate(BaseModel):
    role: str = Field(pattern=r"^(owner|admin|member)$")
    max_uses: int = Field(default=1, ge=1, le=20)
    expires_in_days: int = Field(default=7, ge=1, le=30)


class InvitationCreated(BaseModel):
    id: str
    code: str
    team_id: str
    role: str
    max_uses: int
    used_count: int
    expires_at: str


class InvitationMetadata(BaseModel):
    id: str
    team_id: str
    role: str
    max_uses: int
    used_count: int
    expires_at: str
    revoked_at: str | None
    created_at: str


class InvitationPreview(BaseModel):
    team_id: str
    team_name: str
    role: str
