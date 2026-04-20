from __future__ import annotations

import os
import tempfile
import traceback
import uuid
import base64
import json
import asyncio
import requests
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from google.cloud import storage

from .config import (
    AGE_GROUPS,
    ACTIVITY_DURATION_SECONDS,
    ACTIVITY_LABELS,
    activities_for_group,
    canonical_age_group,
    validate_age_in_group,
    validate_activity_for_group,
)
from .assessment_metrics import build_assessment_metrics
from .csv_results import read_latest_csv_row
from .scoring import score_activity_video
from .logging_utils import get_activity_logger
from activity_common.video_base import read_video_stats
from .schemas import AnalyzeResponse

app = FastAPI(title="FitQuest ML Engine (Pub/Sub Worker)", version="2.0.0")
logger = get_activity_logger()

# --- Pub/Sub Payload Schemas ---
class PubSubMessage(BaseModel):
    data: str
    messageId: str
    attributes: dict | None = None

class PubSubPushPayload(BaseModel):
    message: PubSubMessage
    subscription: str

# --- Internal Configuration ---
TEMP_UPLOAD_DIR = Path(os.getenv("TEMP_UPLOAD_DIR", tempfile.gettempdir())) / "fitquest_processing"
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GCS Helper ---
def download_from_gcs(gcs_uri: str, target_path: Path) -> Path:
    """Downloads a file from a gs:// URI to the local filesystem."""
    try:
        client = storage.Client()
        # Parse gs://bucket-name/path/to/file.mp4
        parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        blob_name = parts[1]
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(str(target_path))
        logger.info(f"GCS_DOWNLOAD_SUCCESS | uri={gcs_uri} | path={target_path}")
        return target_path
    except Exception as exc:
        raise Exception(f"Failed to download from GCS: {exc}")

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": "pubsub-worker"}

# --- The New Async Pub/Sub Endpoint ---
@app.post("/pubsub/process-activity", status_code=200)
async def process_activity_pubsub(payload: PubSubPushPayload):
    out_paths: list[Path] = []
    try:
        # 1. Decode the Pub/Sub base64 message
        decoded_data = base64.b64decode(payload.message.data).decode('utf-8')
        job_data = json.loads(decoded_data)
        
        submission_id = job_data.get("submissionId")
        media_url = job_data.get("mediaUrl")  # Expected: gs://bucket/path.mp4
        media_url_2 = job_data.get("mediaUrl2") # Optional second trial
        activity = job_data.get("activityType")
        webhook_url = job_data.get("webhookUrl")
        child_details = job_data.get("childDetails", {})
        
        name = child_details.get("name", "Unknown")
        age = int(child_details.get("age", 0))
        age_group = canonical_age_group(child_details.get("age_group", ""))
        gender = child_details.get("gender", "male")
        jumped_length = child_details.get("jumped_length")
        jumped_length_2 = child_details.get("jumped_length_2")

        logger.info(f"PUBSUB_JOB_START | submissionId={submission_id} | activity={activity}")

        # 2. Validation
        validate_age_in_group(age_group, age)
        validate_activity_for_group(age_group, activity)
        if activity == "long_jump" and jumped_length is None:
            raise ValueError("Trial 1 jumped distance is required for long jump.")

        # 3. Securely Download Video(s) from GCS
        target_dir = TEMP_UPLOAD_DIR / age_group / activity / submission_id
        target_dir.mkdir(parents=True, exist_ok=True)
        
        ext = Path(media_url).suffix.lower() or ".mp4"
        primary_path = target_dir / f"trial1{ext}"
        download_from_gcs(media_url, primary_path)
        out_paths.append(primary_path)
        
        if media_url_2:
            ext_2 = Path(media_url_2).suffix.lower() or ".mp4"
            secondary_path = target_dir / f"trial2{ext_2}"
            download_from_gcs(media_url_2, secondary_path)
            out_paths.append(secondary_path)

        # 4. Execute ML Processing Pipeline
        jumped_lengths = [jumped_length]
        if media_url_2:
            jumped_lengths.append(jumped_length_2 if jumped_length_2 is not None else jumped_length)

        trial_results = []
        trial_csv_results = []
        trial_durations = []
        
        for index, out_path in enumerate(out_paths):
            trial_candidate_id = f"{submission_id}_T{index+1}"
            result = await asyncio.to_thread(
                score_activity_video,
                activity=activity,
                video_path=out_path,
                age_group=age_group,
                candidate_id=trial_candidate_id,
                candidate_name=name,
                age=age,
                gender=gender,
                jumped_length=jumped_lengths[index] if index < len(jumped_lengths) else jumped_length,
                progress_request_id=submission_id,
            )
            csv_result = read_latest_csv_row(activity, candidate_id=trial_candidate_id, video_path=str(out_path))
            trial_results.append(result)
            trial_csv_results.append(csv_result)
            trial_durations.append(result.duration_seconds)

        metrics_source_rows = [csv_item.get("row", {}) if isinstance(csv_item, dict) else {} for csv_item in trial_csv_results]
        
        activity_metrics, computed_score, computed_max_score, computed_category = build_assessment_metrics(
            activity=activity,
            age_group=age_group,
            candidate_name=name,
            age=age,
            gender=gender,
            trial_rows=metrics_source_rows,
            trial_durations=trial_durations,
            jumped_lengths=jumped_lengths,
            landing_stabilities=[None] * len(out_paths), # Assuming handled natively if missing
        )

        computed_duration = round(sum(trial_durations) / max(1, len(trial_durations)), 2)

        # 5. Construct Final Payload
        final_payload = {
            "submissionId": submission_id,
            "status": "completed",
            "evaluation": {
                "score": computed_score,
                "max_score": computed_max_score,
                "category": computed_category,
                "duration_seconds": computed_duration,
                "activity_metrics": activity_metrics
            }
        }

        # 6. Post Webhook back to Node.js Backend
        if webhook_url:
            response = requests.post(webhook_url, json=final_payload, timeout=10)
            response.raise_for_status()
            logger.info(f"WEBHOOK_SUCCESS | submissionId={submission_id}")

        return {"status": "success", "message": "Job processed and webhook fired."}

    except requests.exceptions.RequestException as exc:
        logger.error(f"WEBHOOK_FAILED | submissionId={submission_id} | error={exc}")
        # Raising an exception will cause a 500, making Pub/Sub retry the message
        raise HTTPException(status_code=500, detail="Failed to deliver webhook.")
    
    except Exception as exc:
        print("\n" + "="*50)
        print("🚨 ML ENGINE CRASHED! HERE IS THE EXACT REASON:")
        traceback.print_exc() 
        print("="*50 + "\n")
        logger.exception(f"PUBSUB_JOB_FATAL_ERROR | error={exc}")
        raise HTTPException(status_code=500, detail=str(exc))
        
    finally:
        # Crucial stateless cleanup
        for path in out_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("common_backend.app:app", host="0.0.0.0", port=port, reload=False)