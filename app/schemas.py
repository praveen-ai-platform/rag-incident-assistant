from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Document(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(default='', max_length=256)
    text: str = Field(min_length=1, max_length=20000)

class IngestRequest(StrictModel):
    docs: list[Document] = Field(min_length=1, max_length=200)

class AskRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)
    min_score: float = Field(default=0.1, gt=0, le=1)
    service: str | None = Field(default=None,min_length=1,max_length=128)
    include_live_context: bool = False

class Evidence(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    score: float
    snippet: str
    source_type: str = "knowledge_base"
    source_uri: str = ""

class SuggestedCheck(BaseModel):
    text: str
    source_chunk_id: str

class Answer(BaseModel):
    status: str
    answer_mode: str
    summary: str
    suggested_checks: list[SuggestedCheck]
    evidence: list[Evidence]
    potential_root_cause: str | None = None
    potential_resolution: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    live_context: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class IngestResult(BaseModel):
    status: str
    docs_ingested: int
    chunks_indexed: int
    mode: str
