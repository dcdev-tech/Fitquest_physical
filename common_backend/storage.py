from pathlib import Path
import ast
import json
import os
from typing import Dict, Any, List

from .logging_utils import get_activity_logger

RESULTS_DIR = Path("common_backend") / "results"
SCORES_FILE = RESULTS_DIR / "scores.json"
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "FitQuest_Physical_database")
logger = get_activity_logger()


def ensure_storage() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not SCORES_FILE.exists():
        SCORES_FILE.write_text("[]", encoding="utf-8")


def append_score_record(record: Dict[str, Any]) -> Path:
    ensure_storage()
    existing: List[Dict[str, Any]]
    try:
        existing = json.loads(SCORES_FILE.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    except json.JSONDecodeError:
        existing = []

    existing.append(record)
    SCORES_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return SCORES_FILE


def _normalized_mongo_uri(uri: str) -> str:
    # User-provided URI can come as mongodb://localhost://27017; normalize it.
    if uri.startswith("mongodb://localhost://"):
        return uri.replace("mongodb://localhost://", "mongodb://localhost:", 1)
    return uri


def _mongo_client():
    from pymongo import MongoClient

    raw_uri = os.getenv("MONGO_URI", "mongodb://localhost://27017")
    uri = _normalized_mongo_uri(raw_uri)
    return MongoClient(uri, serverSelectionTimeoutMS=3000)


def _activity_collection_name(activity: str) -> str:
    return f"{activity}_results"


def _activity_vars_collection_name(activity: str) -> str:
    return f"{activity}_calculation_variables"


def _resolve_db_name(client) -> str:
    target = MONGO_DB_NAME
    try:
        existing_names = client.list_database_names()
    except Exception:
        return target

    lookup = {name.lower(): name for name in existing_names}
    return lookup.get(target.lower(), target)


def _parse_csv_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return text
    if text.startswith("[") and text.endswith("]"):
        try:
            return ast.literal_eval(text)
        except Exception:
            return text
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


NON_METRIC_KEYS = {
    "ID",
    "Name",
    "Video_path",
}


def extract_calculation_variables(activity: str, csv_result: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(csv_result, dict):
        return {}
    row = csv_result.get("row")
    if not isinstance(row, dict):
        return {}
    return {
        k: _parse_csv_value(v)
        for k, v in row.items()
        if k not in NON_METRIC_KEYS
    }


def persist_record_to_mongodb(record: Dict[str, Any], csv_result: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Persist to MongoDB collections:
    - users
    - children
    - <activity>_results (activity-specific collection)
    - data_storage (CSV-equivalent storage)
    """
    status: Dict[str, Any] = {
        "ok": False,
        "db": MONGO_DB_NAME,
        "error": None,
        "collections": [],
    }

    try:
        from pymongo.errors import PyMongoError

        client = _mongo_client()
        client.admin.command("ping")
        resolved_db_name = _resolve_db_name(client)
        status["db"] = resolved_db_name
        db = client[resolved_db_name]
        logger.info(
            "MONGO_CONNECT_OK | db=%s | activity=%s | candidate_id=%s",
            resolved_db_name,
            record.get("activity"),
            record.get("candidate_id"),
        )

        users = db["users"]
        children = db["children"]
        activity_results = db[_activity_collection_name(record["activity"])]
        activity_vars = db[_activity_vars_collection_name(record["activity"])]
        data_storage = db["data_storage"]

        user_doc = {
            "name": record.get("name"),
            "updated_at": record.get("created_at"),
        }
        users.update_one({"name": user_doc["name"]}, {"$set": user_doc}, upsert=True)
        status["collections"].append("users")
        logger.info("MONGO_WRITE_OK | collection=users | candidate_id=%s", record.get("candidate_id"))

        child_doc = {
            "candidate_id": record.get("candidate_id"),
            "name": record.get("name"),
            "age": record.get("age"),
            "age_group": record.get("age_group"),
            "gender": record.get("gender"),
            "updated_at": record.get("created_at"),
        }
        children.update_one({"candidate_id": child_doc["candidate_id"]}, {"$set": child_doc}, upsert=True)
        status["collections"].append("children")
        logger.info("MONGO_WRITE_OK | collection=children | candidate_id=%s", record.get("candidate_id"))

        activity_results.insert_one(record)
        status["collections"].append(_activity_collection_name(record["activity"]))
        logger.info(
            "MONGO_WRITE_OK | collection=%s | candidate_id=%s",
            _activity_collection_name(record["activity"]),
            record.get("candidate_id"),
        )

        calc_vars_doc = {
            "created_at": record.get("created_at"),
            "candidate_id": record.get("candidate_id"),
            "activity": record.get("activity"),
            "age_group": record.get("age_group"),
            "name": record.get("name"),
            "calculation_variables": extract_calculation_variables(record["activity"], csv_result),
        }
        activity_vars.insert_one(calc_vars_doc)
        status["collections"].append(_activity_vars_collection_name(record["activity"]))
        logger.info(
            "MONGO_WRITE_OK | collection=%s | candidate_id=%s",
            _activity_vars_collection_name(record["activity"]),
            record.get("candidate_id"),
        )

        csv_row = (csv_result or {}).get("row") if isinstance(csv_result, dict) else None
        data_storage_doc = {
            "created_at": record.get("created_at"),
            "candidate_id": record.get("candidate_id"),
            "activity": record.get("activity"),
            "name": record.get("name"),
            "age": record.get("age"),
            "csv_row": csv_row,
            "record": record,
        }
        data_storage.insert_one(data_storage_doc)
        status["collections"].append("data_storage")
        logger.info("MONGO_WRITE_OK | collection=data_storage | candidate_id=%s", record.get("candidate_id"))

        status["ok"] = True
        return status
    except PyMongoError as exc:
        status["error"] = str(exc)
        logger.exception(
            "MONGO_WRITE_FAIL | db=%s | activity=%s | candidate_id=%s | error=%s",
            status.get("db"),
            record.get("activity"),
            record.get("candidate_id"),
            exc,
        )
        return status
    except Exception as exc:
        status["error"] = str(exc)
        logger.exception(
            "MONGO_WRITE_FAIL | db=%s | activity=%s | candidate_id=%s | error=%s",
            status.get("db"),
            record.get("activity"),
            record.get("candidate_id"),
            exc,
        )
        return status
