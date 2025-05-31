from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import whisper
import os
import uuid
import logging
import yt_dlp

from google import genai
from google.genai import types

# --- Setup FastAPI ---
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO)

# Load Whisper model once
logging.info("Loading Whisper model...")
whisper_model = whisper.load_model("tiny")
logging.info("Model loaded.")


# --- Models ---
class TranscribeRequest(BaseModel):
    url: str


class ChatRequest(BaseModel):
    summary: str
    userQuestion: str
    title: str


# --- Gemini Setup ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# --- Transcribe Route ---
@app.post("/transcribe/")
async def transcribe_youtube(request: TranscribeRequest):
    video_id = request.url.strip()
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    base_filename = f"audio_{uuid.uuid4()}"
    audio_filename = f"{base_filename}.mp3"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": base_filename,
        "quiet": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "noplaylist": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",  # Important to avoid 403
    }

    try:
        logging.info(f"Downloading audio from: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            title = info.get("title", "")
            description = info.get("description", "")

        logging.info("Download complete. Starting transcription...")
        result = whisper_model.transcribe(audio_filename)
        logging.info("Transcription complete.")

        os.remove(audio_filename)
        logging.info("Temporary file removed.")

        return {
            "response": {
                "title": title,
                "description": description,
                "video_content": result["text"],
            }
        }

    except Exception as e:
        logging.error(f"Error in /transcribe: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error during transcription: {str(e)}"
        )


# --- Chat Route ---
@app.post("/chat")
async def chat_with_summary(request: ChatRequest):
    try:
        prompt_template = """You just watched a YouTube video.

Title: {title}

Transcript:
{summary}

Answer the user's question as if you're explaining it to a friend.

Guidelines:
- Don't mention you're an AI or refer to the transcript.
- Do not include any prefixes like "System:" or "User:". 
- Use general world knowledge when appropriate (e.g., speaker name, organization).
- Use the transcript only when the question is about specific content in the video.
- Always create the response in visually appealing markdown string format.
- If the question is unrelated to the video, politely mention that it's not covered in the video, but still answer it briefly based on general knowledge.

Example response to an unrelated question:
"That topic isn't really covered in this video, but here's a quick answer anyway: ..."

Question: {userQuestion}
"""
        full_prompt = prompt_template.format(
            title=request.title,
            summary=request.summary,
            userQuestion=request.userQuestion,
        )

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=full_prompt)],
            )
        ]

        generate_config = types.GenerateContentConfig(response_mime_type="text/plain")

        response_text = ""
        for chunk in gemini_client.models.generate_content_stream(
            model="gemini-2.5-flash-preview-04-17",
            contents=contents,
            config=generate_config,
        ):
            if chunk.text:
                response_text += chunk.text

        return {"response": response_text.strip()}

    except Exception as e:
        logging.error(f"Error in /chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
