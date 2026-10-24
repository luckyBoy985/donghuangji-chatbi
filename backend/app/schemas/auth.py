from pydantic import BaseModel, ConfigDict, Field, field_validator


USERNAME_PATTERN = r"^[a-z0-9._-]{3,40}$"


class SetupRequest(BaseModel):
    bootstrap_token: str = Field(min_length=1, max_length=512)
    username: str = Field(pattern=USERNAME_PATTERN)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("显示名称不能为空")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class TeamRoleInfo(BaseModel):
    id: str
    name: str
    role: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    platform_role: str
    status: str
    must_change_password: bool = False
    teams: list[TeamRoleInfo] = Field(default_factory=list)


class SetupStatus(BaseModel):
    setup_required: bool


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("显示名称不能为空")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
