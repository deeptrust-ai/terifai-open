import os
import uuid
from io import BytesIO

import requests
from dotenv import load_dotenv
from modal import App, Image

load_dotenv()

image = (
    Image.debian_slim()
    .pip_install("requests", "python-dotenv")
    .env(
        {
            "ELEVENLABS_API_KEY": os.getenv("ELEVENLABS_API_KEY"),
            "CARTESIA_API_KEY": os.getenv("CARTESIA_API_KEY"),
        }
    )
)
app = App("terifai-functions", image=image)


@app.function()
def add_elevenlabs_voice(audio: bytes):
    url = "https://api.elevenlabs.io/v1/voices/add"
    api_key = os.getenv("ELEVENLABS_API_KEY")

    # Use BytesIO to simulate a file
    audio_file = BytesIO(audio)
    filename = f"audio_{uuid.uuid4().hex[:8]}.wav"

    files = {"files": (filename, audio_file, "audio/wav")}

    data = {
        "name": f"terifai-{uuid.uuid4().hex[:8]}",
        "description": "Voice added from terifai service.",
    }

    headers = {"xi-api-key": api_key}

    response = requests.post(url, files=files, data=data, headers=headers)

    try:
        response.raise_for_status()  # Raises an HTTPError for bad responses
        voice_id = response.json()["voice_id"]
        print(f"Voice cloning successful: {voice_id}")
        return voice_id
    except requests.exceptions.HTTPError as e:
        print(f"Error in voice cloning: {e}")
        print(f"Response content: {response.text}")
        raise


@app.function()
def add_cartesia_voice(audio: bytes):
    # First get embedding from clip endpoint
    clip_url = "https://api.cartesia.ai/voices/clone/clip"
    api_key = os.getenv("CARTESIA_API_KEY")

    # Use BytesIO to simulate a file
    audio_file = BytesIO(audio)
    filename = f"audio_{uuid.uuid4().hex[:8]}.wav"

    files = {"clip": (filename, audio_file, "audio/wav")}
    data = {"enhance": "true"}

    headers = {"X-API-Key": api_key, "Cartesia-Version": "2024-06-10"}

    clip_response = requests.post(clip_url, files=files, data=data, headers=headers)

    try:
        clip_response.raise_for_status()
        embedding = clip_response.json()["embedding"]
        print("Successfully got voice embedding")

        # Create voice with embedding
        create_url = "https://api.cartesia.ai/voices/"

        voice_data = {
            "name": f"terifai-{uuid.uuid4().hex[:8]}",
            "description": "Voice added from terifai service",
            "embedding": embedding,
            "language": "en",
        }

        headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json",
        }

        create_response = requests.post(create_url, json=voice_data, headers=headers)
        create_response.raise_for_status()

        voice_id = create_response.json()["id"]
        print(f"Voice creation successful: {voice_id}")
        return voice_id

    except requests.exceptions.HTTPError as e:
        print(f"Error in voice cloning: {e}")
        print(
            f"Response content: {clip_response.text if e.response == clip_response else create_response.text}"
        )
        raise
