import os
import subprocess
import sys
import time
import uuid
from typing import Dict, Optional, Tuple

import requests
from loguru import logger

FLY_API_HOST = os.getenv("FLY_API_HOST", "https://api.machines.dev/v1")
FLY_APP_NAME = os.getenv("FLY_APP_NAME")
FLY_API_KEY = os.getenv("FLY_API_KEY")
FLY_HEADERS = {
    "Authorization": f"Bearer {FLY_API_KEY}",
    "Content-Type": "application/json",
}

MAX_RETRIES = 24
RETRY_DELAY = 5

# Store local bot processes: bot_id -> (process, room_url)
local_bots: Dict[str, Tuple[subprocess.Popen, str]] = {}


def spawn_local(room_url: str, token: str, selected_prompt: str, voice_id: str = "") -> str:
    """Spawn a local bot process and return its ID"""
    bot_id = str(uuid.uuid4())
    logger.info(f"Spawning local bot with id: {bot_id}")

    # Get the project root directory (parent of backend)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Create and start the process with PYTHONPATH set
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root

    # Create and start the process
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "backend.bot",
            f"--room_url={room_url}",
            f"--token={token}",
            f"--prompt={selected_prompt}",
            f"--voice_id={voice_id}",
        ],
        env=env,
        cwd=project_root,
        bufsize=1,
    )

    # Store the process and room_url
    local_bots[bot_id] = (proc, room_url)

    return bot_id


def spawn_fly(room_url: str, token: str, selected_prompt: str, voice_id: str = "") -> str:
    """Spawn a fly machine and return its ID"""
    # Use the same image as the bot runner
    logger.debug(
        f"Getting machine info from Fly: {FLY_API_HOST}/apps/{FLY_APP_NAME}/machines"
    )
    res = requests.get(
        f"{FLY_API_HOST}/apps/{FLY_APP_NAME}/machines", headers=FLY_HEADERS
    )
    if res.status_code != 200:
        raise Exception(f"Unable to get machine info from Fly: {res.text}")
    image = res.json()[0]["config"]["image"]

    # Machine configuration
    cmd = f"python -m backend.bot --room_url {room_url} --token {token} --prompt {selected_prompt} --voice_id {voice_id}"
    cmd = cmd.split()
    worker_props = {
        "config": {
            "image": image,
            "auto_destroy": True,
            "init": {
                "cmd": cmd,
                # "env": {"PYTHONPATH": "../"},
            },
            "restart": {"policy": "no"},
            "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 2048},
        },
    }

    # Spawn a new machine instance
    res = requests.post(
        f"{FLY_API_HOST}/apps/{FLY_APP_NAME}/machines",
        headers=FLY_HEADERS,
        json=worker_props,
    )

    if res.status_code != 200:
        raise Exception(f"Problem starting a bot worker: {res.text}")

    # Wait for the machine to enter the started state
    vm_id = res.json()["id"]

    for _ in range(MAX_RETRIES):
        state = get_fly_status(vm_id)

        if state == "started":
            return vm_id

        time.sleep(RETRY_DELAY)

    raise Exception(f"Bot failed to enter started state after {MAX_RETRIES} retries")


def spawn(room_url: str, token: str, selected_prompt: str, voice_id: str = "", local: bool = False) -> str:
    """Unified interface to spawn a bot either locally or on Fly"""
    logger.debug(
        f"Spawning bot with room_url: {room_url} and token: {token}, local: {local}"
    )
    if local:
        return spawn_local(room_url, token, selected_prompt, voice_id)
    else:
        return spawn_fly(room_url, token, selected_prompt, voice_id)


def get_fly_status(vm_id: str) -> str:
    """Get status of a Fly machine"""
    res = requests.get(
        f"{FLY_API_HOST}/apps/{FLY_APP_NAME}/machines/{vm_id}", headers=FLY_HEADERS
    )
    return res.json()["state"]


def get_local_status(bot_id: str) -> Optional[str]:
    """Get status of a local bot process"""
    if bot_id not in local_bots:
        return None

    proc, _ = local_bots[bot_id]
    returncode = proc.poll()

    if returncode is None:
        return "started"
    else:
        # Clean up finished processes
        proc.wait()
        del local_bots[bot_id]
        return "stopped"


def get_status(bot_id: str, local: bool = False) -> Optional[str]:
    """Unified interface to get bot status"""
    if local:
        return get_local_status(bot_id)
    else:
        return get_fly_status(bot_id)
