from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

JsonValue = Any


class ParameterSchema(BaseModel):
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
    content_type: str | None = None
    analysis: ResponseAnalysis | None = None
    body: JsonValue = None


class Endpoint(BaseModel):
    method: str
    path: str
    category: str = "unknown"  # "authentication", "navigation", "data", "unknown"
    purpose: str = "unknown"
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    hit_count: int = 1
    first_seen: datetime
    last_seen: datetime
    request: EndpointRequest = Field(default_factory=EndpointRequest)
    response: EndpointResponse = Field(default_factory=EndpointResponse)


class DiscoveryCatalog(BaseModel):
    discovered_at: datetime
    base_url: str
    endpoints: list[Endpoint] = Field(default_factory=list)
