import argparse
import contextlib
import os
import sys
from dataclasses import asdict
import wave
from io import BytesIO
import uuid
import requests
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from backend.helpers import DailyConfig, get_daily_config, get_name_from_url, get_token
from backend.spawn import get_status, spawn

# Bot machine dict for status reporting and concurrency control
bot_machines = {}

MAX_BOTS_PER_ROOM = 1

load_dotenv()

# Get local mode from command line args
def get_local_mode() -> bool:
    if "--local" in sys.argv:
        return True
    return False


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Set state on startup using command line args
    app.state.is_local_mode = get_local_mode()
    logger.info(f"Setting local mode to: {app.state.is_local_mode}")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/create")
async def create_room(request: Request) -> JSONResponse:
    body = await request.body()
    if body:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    else:
        data = {}

    if data.get("room_url") is not None:
        room_url = data.get("room_url")
        room_name = get_name_from_url(room_url)
        token = get_token(room_url)
        config = DailyConfig(
            room_url=room_url,
            room_name=room_name,
            token=token,
        )
    else:
        config = get_daily_config()

    return JSONResponse(asdict(config))


class StartAgentItem(BaseModel):
    room_url: str
    token: str
    selected_prompt: str
    voice_id: str
    custom_prompt: str | None

@app.post("/start")
async def start_agent(item: StartAgentItem, request: Request) -> JSONResponse:
    if item.room_url is None or item.token is None:
        raise HTTPException(status_code=400, detail="room_url and token are required")

    room_url = item.room_url
    token = item.token
    selected_prompt = item.selected_prompt
    voice_id = item.voice_id
    custom_prompt = item.custom_prompt

    try:
        local = request.app.state.is_local_mode
        bot_id = spawn(room_url, token, selected_prompt, voice_id=voice_id, local=local, custom_prompt=custom_prompt)
        bot_machines[bot_id] = room_url
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {e}")

    return JSONResponse({"bot_id": bot_id, "room_url": room_url})


@app.get("/status/{bot_id}")
def get_bot_status(bot_id: str, request: Request):
    # Look up the machine/process
    if bot_id not in bot_machines:
        raise HTTPException(status_code=404, detail=f"Bot with id: {bot_id} not found")

    # Check the status
    status = get_status(bot_id, local=request.app.state.is_local_mode)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Bot with id: {bot_id} not found")

    return JSONResponse({"bot_id": bot_id, "status": status})


@app.post("/clone_voice")
async def clone_voice(voice_file: UploadFile = File(...)) -> JSONResponse:
    try:

        audio = await voice_file.read()

        url = "https://api.cartesia.ai/voices/clone"
        api_key = os.getenv("CARTESIA_API_KEY")

        # Use BytesIO to simulate a file
        audio_file = BytesIO(audio)
        filename = f"audio_{uuid.uuid4().hex[:8]}.wav"

        files = {"clip": (filename, audio_file, "audio/wav")}
        data = {
            "name": "Terifai Voice Clone",
            "language": "en",
            "mode": "stability",
            "enhance": True,
        }

        headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": "2024-06-10"
        }
        try:
            response = requests.post(url, data=data, files=files, headers=headers)
            response.raise_for_status()
            voice_id = response.json()["id"]
            print(f"Voice creation successful: {voice_id}")
            return voice_id
        except requests.exceptions.HTTPError as e:
            print(f"Error response from API: {str(e.response)}")
            raise

    except Exception as e:
        print(f"Error in clone_voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Check environment variables
    required_env_vars = [
        "OPENAI_API_KEY",
        "DAILY_API_KEY",
        "ELEVENLABS_VOICE_ID",
        "ELEVENLABS_API_KEY",
    ]

    # Only check Fly-related env vars if not in local mode
    fly_env_vars = [
        "FLY_API_KEY",
        "FLY_APP_NAME",
    ]

    parser = argparse.ArgumentParser(description="TerifAI FastAPI server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=7860, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Reload code on change")
    parser.add_argument(
        "--local", action="store_true", help="Run bots locally instead of on Fly"
    )

    args = parser.parse_args()

    # Check environment variables
    for env_var in required_env_vars:
        if env_var not in os.environ:
            raise Exception(f"Missing environment variable: {env_var}.")

    if not args.local:
        for env_var in fly_env_vars:
            if env_var not in os.environ:
                raise Exception(f"Missing environment variable: {env_var}.")

    import uvicorn

    uvicorn.run(
        "backend.server:app", host=args.host, port=args.port, reload=args.reload
    )
