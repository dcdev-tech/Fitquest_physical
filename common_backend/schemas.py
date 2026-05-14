from pydantic import BaseModel, Field

class AnalyzeResponse(BaseModel):
    name: str
    age: float
    age_group: str
    activity: str
    score: float
    max_score: float = Field(default=20)
    category: str
    duration_seconds: float
    csv_result: dict | None = None
    activity_metrics: dict | None = None
