import uuid
import time
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="AegisCX Mock API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DUMMY DATA ---
MOCK_TOKEN = "mock-jwt-token-123456"

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    company_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/register")
@app.post("/api/auth/login")
async def login_or_register():
    return {
        "access_token": MOCK_TOKEN,
        "refresh_token": "mock-refresh",
        "token_type": "bearer",
        "expires_in": 3600
    }

@app.get("/api/auth/me")
async def get_me():
    return {
        "id": "user-123",
        "email": "soumoditt@gmail.com",
        "name": "Soumo",
        "role": "admin",
        "company_id": "company-123",
        "created_at": "2026-04-20T00:00:00Z"
    }

@app.get("/api/recordings/")
async def list_recordings():
    return {
        "items": [
            {
                "id": "demo-recording-1",
                "original_filename": "customer_interview.mp4",
                "status": "ANALYZED",
                "file_size_bytes": 14500000,
                "duration_seconds": 300.0,
                "format": "mp4",
                "created_at": "2026-04-20T00:00:00Z",
                "updated_at": "2026-04-20T00:05:00Z"
            }
        ],
        "total": 1,
        "page": 1,
        "per_page": 20,
        "pages": 1
    }

@app.post("/api/recordings/upload")
async def upload_recording(file: UploadFile = File(...)):
    return {
        "recording_id": "demo-recording-1",
        "task_id": "task-123",
        "status": "ANALYZED",
        "message": "Mock Upload successful"
    }

@app.get("/api/recordings/{rec_id}")
async def get_recording(rec_id: str):
    return {
        "id": rec_id,
        "original_filename": "demo_video.mp4",
        "status": "ANALYZED",
        "file_size_bytes": 15000000,
        "duration_seconds": 340.5,
        "format": "mp4",
        "created_at": "2026-04-20T00:00:00Z",
        "updated_at": "2026-04-20T00:05:00Z"
    }

@app.get("/api/recordings/{rec_id}/status")
async def get_recording_status(rec_id: str):
    return {
        "recording_id": rec_id,
        "status": "ANALYZED",
        "progress_message": "Analysis complete",
        "error_message": None,
        "duration_seconds": 300.0
    }

@app.get("/api/recordings/{rec_id}/transcript")
async def get_recording_transcript(rec_id: str):
    return {
        "recording_id": rec_id,
        "full_text": "Hello, I wanted to talk about my recent experience with AegisCX. It was fantastic. The UI is very clean.",
        "word_count": 21,
        "language": "en",
        "num_speakers": 1,
        "stt_model": "whisper-mock",
        "segments": [
            {
                "segment_index": 0,
                "speaker_label": "SPEAKER_00",
                "start_time": 0.0,
                "end_time": 5.0,
                "text": "Hello, I wanted to talk about my recent experience with AegisCX. It was fantastic. The UI is very clean.",
                "word_count": 21
            }
        ]
    }

@app.get("/api/recordings/{rec_id}/insights")
async def get_recording_insights(rec_id: str):
    return {
        "recording_id": rec_id,
        "overall_sentiment": "positive",
        "sentiment_score": 0.95,
        "dominant_emotion": "joy",
        "customer_intent": "feedback",
        "intent_confidence": 0.88,
        "executive_summary": "The customer expressed high satisfaction with the platform.",
        "product_mentions": [{"entity": "AegisCX", "sentiment": "positive"}],
        "behavioral_signals": {"frustration_score": 0.0, "churn_risk": "low"},
        "emotion_arc": [{"time": 0.0, "emotion": "joy"}],
        "confidence_score": 0.92,
        "analysis_tier": "basic",
        "requires_human_review": False,
        "full_analysis": {}
    }

@app.get("/api/analytics/company")
async def get_analytics(timeframe: str = "30d"):
    return {
        "total_recordings": 1,
        "total_duration_hours": 0.08,
        "average_sentiment": 0.95,
        "sentiment_distribution": {"positive": 1, "negative": 0, "neutral": 0, "mixed": 0},
        "top_emotions": {"joy": 1},
        "intents": {"feedback": 1},
        "sentiment_trend": [{"date": "2026-04-20", "avg_sentiment": 0.95}]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
