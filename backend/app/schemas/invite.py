from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.auth import USERNAME_PATTERN


class InviteRegistration(BaseModel):
    code: str = Field(min_length=20, max_length=200)
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
