from pydantic import BaseModel, Field, field_validator


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    products: list[str] = Field(default_factory=lambda: ["东煌纪"])
    sections: list[str] = Field(default_factory=list)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value
