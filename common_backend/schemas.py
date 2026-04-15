from pydantic import BaseModel, Field


class AnalyzeResponse(BaseModel):
    name: str
    age: int
    age_group: str
    activity: str
    score: float
    max_score: float = Field(default=20)
    category: str
    duration_seconds: float
    video_path: str
    saved_record_path: str
    csv_result: dict | None = None
    activity_metrics: dict | None = None
