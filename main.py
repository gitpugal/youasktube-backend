from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pytubefix import YouTube
import whisper
import os
import uuid
import logging

from google import genai
from google.genai import types

# --- Setup FastAPI ---
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# Define request models
class TranscribeRequest(BaseModel):
    url: str


class ChatRequest(BaseModel):
    summary: str
    userQuestion: str
    title: str


# --- Gemini Client Setup ---
GEMINI_API_KEY= os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
gemini_model = "gemini-2.0-flash"


# --- /chat Route using Gemini ---
@app.post("/chat")
async def chat_with_summary(request: ChatRequest):
    try:
        prompt_template = """You just watched a YouTube video.

Title: {title}

Transcript:
{summary}

Answer the user's question as if you're explaining it to a friend.

Guidelines:
- Be casual and direct.
- Don't mention you're an AI or refer to the transcript.
- Do not include any prefixes like "System:" or "User:".
- Use general world knowledge when appropriate (e.g., speaker name, organization).
- Use the transcript only when the question is about specific content in the video.
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
        print(full_prompt)
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"""{full_prompt}""")],
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


# --- /transcribe Route ---
@app.post("/transcribe/")
async def transcribe_youtube(request: TranscribeRequest):
    url = request.url.strip()
    try:
        logging.info(f"Downloading audio from: {url}")
        yt = YouTube(f"https://www.youtube.com/watch?v={url}")

        stream = yt.streams.filter(only_audio=True).first()
        if not stream:
            raise HTTPException(status_code=404, detail="No audio stream found.")

        filename = f"audio_{uuid.uuid4()}.mp4"
        logging.info(f"Downloading stream to {filename}...")
        stream.download(filename=filename)
        logging.info("Download complete.")

        logging.info("Starting transcription...")
        result = whisper_model.transcribe(filename)
        logging.info("Transcription done.")

        os.remove(filename)
        logging.info("Temp file removed.")

        return {
            "response": {
                "title": yt.title,
                "description": yt.description,
                "video_content": result["text"],
            }
        }

    except Exception as e:
        logging.error(f"Error in /transcribe: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error during transcription: {str(e)}"
        )
