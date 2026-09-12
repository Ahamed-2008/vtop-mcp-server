from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

JsonValue = Any


class ParameterSchema(BaseModel):
    location: str = "query"  # "query", "form", "path", "hidden"
    examples: list[str] = Field(default_factory=list)
    type: str = "string"
    dynamic: bool = False
    required: bool = True
    description: str | None = None


class ResponseAnalysis(BaseModel):
    title: str | None = None
    headings: list[str] = Field(default_factory=list)
    table_headers: list[str] = Field(default_factory=list)
    form_fields: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    data_keys: list[str] = Field(default_factory=list)
    produced_fields: dict[str, list[str]] = Field(default_factory=dict)


class CapturedRequest(BaseModel):
    method: str
    url: str
    path: str
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    body: JsonValue = None
    resource_type: str = "other"
    timestamp: datetime


class CapturedResponse(BaseModel):
    status: int | None = None
    content_type: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    body: JsonValue = None


class CapturedExchange(BaseModel):
    request: CapturedRequest
    response: CapturedResponse | None = None
    purpose: str = "unknown"


class EndpointRequest(BaseModel):
    parameters: dict[str, ParameterSchema] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    body: JsonValue = None


class EndpointResponse(BaseModel):
    status: int | None = None
    status_codes: list[int] = Field(default_factory=list)
    content_type: str | None = None
    analysis: ResponseAnalysis | None = None
    body: JsonValue = None


class Endpoint(BaseModel):
    id: str | None = None
    name: str | None = None
    method: str
    path: str
    classification: str = "READ"  # "READ", "UNKNOWN_WRITE_OR_UNSAFE", "AUTH", "NAVIGATION"
    category: str = "unknown"  # "authentication", "navigation", "data", "unknown"
    purpose: str = "unknown"
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    hit_count: int = 1
    first_seen: datetime
    last_seen: datetime
    request: EndpointRequest = Field(default_factory=EndpointRequest)
    response: EndpointResponse = Field(default_factory=EndpointResponse)


class WorkflowDependency(BaseModel):
    parameter: str
    produced_by: str
    consumed_by: str


class Workflow(BaseModel):
    name: str = "workflow"
    steps: list[str] = Field(default_factory=list)
    dependencies: list[WorkflowDependency] = Field(default_factory=list)


class EndpointInventory(BaseModel):
    generated_at: datetime | None = None
    discovered_at: datetime | None = None
    base_domains: list[str] = Field(default_factory=list)
    base_url: str | None = None
    endpoints: dict[str, Endpoint] | list[Endpoint] = Field(default_factory=dict)
    workflows: list[Workflow] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.generated_at is None and self.discovered_at is not None:
            self.generated_at = self.discovered_at
        elif self.discovered_at is None and self.generated_at is not None:
            self.discovered_at = self.generated_at

        if not self.base_domains and self.base_url:
            self.base_domains = [self.base_url]
        elif self.base_domains and not self.base_url:
            self.base_url = self.base_domains[0]


# Alias for backwards compatibility
DiscoveryCatalog = EndpointInventory


