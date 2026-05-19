from pydantic import BaseModel
from typing import Optional

class AnalysisRequest(BaseModel):
    query: str

