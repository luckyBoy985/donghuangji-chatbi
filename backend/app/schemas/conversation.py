from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    title: str | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value[:120]


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    citation_key: str
    chunk_id: str
    doc_id: str
    product: str
    section: str
    title: str
    source_type: str
    published_at: str
    url: str
    snippet: str
    score: float
    used_in_answer: bool


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    status: str
    generation_status: str
    model: str
    created_at: str
    citations: list[CitationOut] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_user_id: str
    access_role: str = "owner"
    title: str
    created_at: str
    updated_at: str


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut] = Field(default_factory=list)


class ShareUpdate(BaseModel):
    team_ids: list[str] = Field(default_factory=list)


class ShareOut(BaseModel):
    id: str
    conversation_id: str
    team_id: str
    team_name: str
    created_at: str
