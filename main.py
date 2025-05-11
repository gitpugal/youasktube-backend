from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pytubefix import YouTube
import whisper
import os
import uuid
import logging

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(level=logging.INFO)

# Load Whisper model once
logging.info("Loading Whisper model...")
model = whisper.load_model("base")
logging.info("Model loaded.")

@app.get("/transcribe/")
async def transcribe_youtube(url: str):
    try:
        logging.info(f"Downloading audio from: {url}")

        yt = YouTube(url)  # pytubefix replaces pytube YouTube class
        
        logging.info("Available audio streams:")
        for stream in yt.streams.filter(only_audio=True):
            logging.info(f"Stream itag={stream.itag}, mime_type={stream.mime_type}, abr={stream.abr}")

        stream = yt.streams.filter(only_audio=True).first()
        if not stream:
            return {"error": "No audio stream found."}

        filename = f"audio_{uuid.uuid4()}.mp4"
        logging.info(f"Downloading stream to {filename}...")
        stream.download(filename=filename)
        logging.info("Download complete.")

        logging.info("Starting transcription...")
        result = model.transcribe(filename)
        logging.info("Transcription done.")

        # Ensure the temp file gets deleted even in case of error
        try:
            os.remove(filename)
            logging.info("Temp file removed.")
        except Exception as e:
            logging.error(f"Error removing temp file: {e}")

        return {"text": f"'title': '{yt.title}','description': '{yt.description}','video_content': '{result['text']}'"}

    except Exception as e:
        logging.error(f"Exception occurred: {e}")
        return {"error": f"Error during transcription: {str(e)}"}
