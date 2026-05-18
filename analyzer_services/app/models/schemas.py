from pydantic import BaseModel

class AnalysisRequest(BaseModel):
    query: str
    thread_id: str | None = None

