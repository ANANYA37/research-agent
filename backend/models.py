"""Pydantic models for request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(RegisterRequest):
    pass


class UserResponse(BaseModel):
    id: str
    email: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CollectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)


class TagCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=48)
    color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")


class ReportMetadataRequest(BaseModel):
    collection_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)


class ResearchRequest(BaseModel):
    """Request model for starting a research session."""
    topic: str = Field(..., description="The research topic to investigate")
    depth: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Number of research iterations (1-5). Higher = deeper research but slower."
    )
    force_fresh: bool = Field(
        default=False,
        description="Bypass saved cache/history and run fresh research."
    )
    visual_planner: bool = Field(
        default=False,
        description="Instruct the agent to generate Mermaid.js diagrams in the report."
    )


class SourceInfo(BaseModel):
    """Information about a source used in the research."""
    title: str = ""
    url: str = ""
    snippet: str = ""


class CollectionInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    report_count: int = 0


class TagInfo(BaseModel):
    id: str
    name: str
    color: str = "#2563eb"
    report_count: int = 0


class ResearchResponse(BaseModel):
    """Response model for a completed research session."""
    report: str = Field(..., description="The final markdown report")
    sources: list[SourceInfo] = Field(default_factory=list, description="Sources cited in the report")
    queries_used: list[str] = Field(default_factory=list, description="Search queries that were executed")
    iterations_completed: int = Field(default=0, description="Number of research loops completed")
    history_id: Optional[str] = Field(default=None, description="Saved history item id")
    from_cache: bool = Field(default=False, description="Whether the response came from saved history")
    citation_verification: dict = Field(default_factory=dict, description="Citation validation summary")
    collections: list[CollectionInfo] = Field(default_factory=list)
    tags: list[TagInfo] = Field(default_factory=list)


class ResearchHistoryItem(ResearchResponse):
    """Saved research result for a previous topic."""
    id: str = Field(..., description="History item id")
    topic: str = Field(..., description="Original research topic")
    depth: int = Field(..., ge=1, le=5, description="Research depth used")
    created_at: str = Field(..., description="When the item was first saved")
    updated_at: str = Field(..., description="When the item was last updated")


class ResearchHistorySummary(BaseModel):
    """Compact saved research result for history lists."""
    id: str
    topic: str
    depth: int
    created_at: str
    updated_at: str
    queries_used: list[str] = Field(default_factory=list)
    iterations_completed: int = 0
    sources_count: int = 0
    collections: list[CollectionInfo] = Field(default_factory=list)
    tags: list[TagInfo] = Field(default_factory=list)


class StatusEvent(BaseModel):
    """Model for SSE status events during research."""
    step: str = Field(..., description="Current step name")
    detail: str = Field(default="", description="Additional detail about the step")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Progress percentage 0-1")
    iteration: int = Field(default=0, description="Current iteration number")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str = "ok"
    service: str = "research-agent"
