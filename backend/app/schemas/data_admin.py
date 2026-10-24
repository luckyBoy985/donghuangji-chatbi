from __future__ import annotations

from pydantic import BaseModel, Field


class IngestJobOut(BaseModel):
    id: str
    kind: str
    status: str
    product: str
    section: str
    title: str
    original_name: str
    object_key: str
    source_id: str | None
    progress: int
    message: str
    stats: dict
    error: str
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class DataDocumentOut(BaseModel):
    doc_id: str
    product: str
    source_type: str
    section: str
    title: str
    published_at: str
    url: str
    original_name: str
    content_hash: str
    chars: int
    status: str
    origin: str
    source_id: str | None
    chunk_count: int = 0
    created_at: str
    updated_at: str


class DataDocumentDetail(DataDocumentOut):
    content: str


class DataDocumentPage(BaseModel):
    items: list[DataDocumentOut]
    total: int
    page: int
    page_size: int


class DataDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    section: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, pattern=r"^(active|archived)$")


class DataSourceOut(BaseModel):
    id: str
    name: str
    kind: str
    crawler_key: str | None
    product: str
    status: str
    last_run_at: str | None
    active_job_id: str | None = None


class CrawlerRunRequest(BaseModel):
    max_pages: int = Field(default=60, ge=1, le=100)


class DataOverviewOut(BaseModel):
    documents: int
    active_documents: int
    archived_documents: int
    chunks: int
    products: list[dict]
    recent_jobs: list[IngestJobOut]
