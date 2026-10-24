from pydantic import BaseModel, Field


class ReportCreate(BaseModel):
    products: list[str] | None = None


class ReportOut(BaseModel):
    id: str
    conversation_id: str
    title: str
    products: list[str] = Field(default_factory=list)
    markdown: str
    html: str
    created_at: str


class ReportSummary(BaseModel):
    id: str
    conversation_id: str
    title: str
    created_at: str
