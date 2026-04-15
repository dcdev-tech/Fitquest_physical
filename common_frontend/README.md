# Common Child Activity App

## Run backend

```powershell
python -m uvicorn common_backend.app:app --host 0.0.0.0 --port 8000 --reload
```

## Run frontend

```powershell
streamlit run common_frontend/streamlit_app.py
```

## JSON score output

Scores are appended to:

`common_backend/results/scores.json`

Each entry stores:
- `name`
- `age`
- `age_group`
- `activity`
- `score`
- `max_score`
- `category`
- `duration_seconds`
- `video_path`
- `created_at`
