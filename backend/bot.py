import argparse
import asyncio
import logging
import os
import time

import aiohttp
from dotenv import load_dotenv

## VAD
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams

## Frames
from pipecat.frames.frames import EndFrame, LLMMessagesFrame

## Pipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

## Processors
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantResponseAggregator,
    LLMUserResponseAggregator,
)

## Services
from pipecat.services.openai import OpenAILLMService

# Pipecat
## Transports
from pipecat.transports.services.daily import DailyParams, DailyTransport

from backend.helpers import get_daily_config
from backend.processors import (
    CartesiaTerrify,
    DeepgramTerrify,
    ElevenLabsTerrify,
    TranscriptionLogger,
    XTTSTerrify,
)
from backend.prompts import (
    LLM_INTRO_PROMPT,
    LLM_BASE_PROMPT,
    LLM_PREUPLOAD_BASE_PROMPT,
    LLM_VOICE_CHANGE_PROMPT_DEFAULT,
    LLM_VOICE_CHANGE_PROMPT_IT_SUPPORT, 
    LLM_VOICE_CHANGE_PROMPT_CORPORATE,
    LLM_VOICE_CHANGE_PROMPT_FINANCE_FRAUD,
    LLM_VOICE_CHANGE_PROMPT_ENGINEERING_BREACH,
    LLM_VOICE_CHANGE_PROMPT_SECURITY_ALERT
)

load_dotenv()

if os.environ.get("DEBUG"):
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

# voice change prompt map
PROMPT_MAP = {
    "default": LLM_VOICE_CHANGE_PROMPT_DEFAULT,
    "it_support": LLM_VOICE_CHANGE_PROMPT_IT_SUPPORT,
    "corporate": LLM_VOICE_CHANGE_PROMPT_CORPORATE,
    "finance_fraud": LLM_VOICE_CHANGE_PROMPT_FINANCE_FRAUD,
    "engineering_breach": LLM_VOICE_CHANGE_PROMPT_ENGINEERING_BREACH,
    "security_alert": LLM_VOICE_CHANGE_PROMPT_SECURITY_ALERT,

}


async def main(room_url, token=None, xtts=False, elevenlabs=False, selected_prompt=None, voice_id="", custom_generated_prompt=None):
    async with aiohttp.ClientSession() as session:
        # -------------- Transport --------------- #

        transport = DailyTransport(
            room_url,
            token,
            "TerifAI",
            DailyParams(
                # audio_in_enabled=True,
                audio_out_enabled=True,
                # transcription_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
                vad_audio_passthrough=True,
            ),
        )

        logging.info("Transport created for room:" + room_url)

        # -------------- Services --------------- #

        stt_service = DeepgramTerrify()

        llm_service = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini"
        )

        if xtts:
            logging.info("Using XTTS")
            tts_service = XTTSTerrify(
                aiohttp_session=session,
                voice_id="Claribel Dervla",
                language="en",
                base_url="https://deeptrust-ai-dev--xtts-xtts-web.modal.run",
            )
        elif elevenlabs:
            logging.info("Using ElevenLabs")
            tts_service = ElevenLabsTerrify(
                aiohttp_session=session,
                api_key=os.getenv("ELEVENLABS_API_KEY"),
            )
        else:
            logging.info("Using Cartesia")
            tts_service = CartesiaTerrify(selected_prompt=selected_prompt, voice_id=voice_id, custom_generated_prompt=custom_generated_prompt)

        # --------------- Setup ----------------- #

        if voice_id:
            if selected_prompt == "custom":
                LLM_START_PROMPT = {
                    "role": "system",
                    "content": custom_generated_prompt
                }
                llm_base_prompt = LLM_PREUPLOAD_BASE_PROMPT
            else:
                LLM_START_PROMPT = {
                    "role": "system",
                    "content": PROMPT_MAP[selected_prompt]
                }
                llm_base_prompt = LLM_PREUPLOAD_BASE_PROMPT
        else:
            LLM_START_PROMPT = LLM_INTRO_PROMPT
            llm_base_prompt = LLM_BASE_PROMPT

        message_history = [llm_base_prompt]

        # We need aggregators to keep track of user and LLM responses
        llm_responses = LLMAssistantResponseAggregator(message_history)
        user_responses = LLMUserResponseAggregator(message_history)
        transcription_logger = TranscriptionLogger()

        # -------------- Pipeline ----------------- #

        pipeline = Pipeline(
            [
                # Transport user input
                transport.input(),
                # STT
                stt_service,
                # Transcription logger
                transcription_logger,
                # User responses
                user_responses,
                # LLM
                llm_service,
                # TTS
                tts_service,
                # Transport bot output
                transport.output(),
                # Assistant spoken responses
                llm_responses,
            ]
        )

        task = PipelineTask(
            pipeline,
            PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                report_only_initial_ttfb=True,
            ),
        )

        # --------------- Events ----------------- #

        # When the first participant joins, the bot should introduce itself.
        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            # Kick off the conversation.
            logging.info(f"Participant joined: {participant['id']}")
            transport.capture_participant_transcription(participant["id"])
            time.sleep(1)
            await task.queue_frame(LLMMessagesFrame([LLM_START_PROMPT]))

        # When the participant leaves, we exit the bot.
        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            logging.info(f"Participant left: {participant['id']}")
            await task.queue_frame(EndFrame())

        # If the call is ended make sure we quit as well.
        @transport.event_handler("on_call_state_updated")
        async def on_call_state_updated(transport, state):
            if state == "left":
                await task.queue_frame(EndFrame())

        # --------------- Runner ----------------- #

        runner = PipelineRunner()

        await runner.run(task)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TerifAI Bot")
    parser.add_argument("--room_url", type=str, help="Room URL")
    parser.add_argument("--token", type=str, help="Token")
    parser.add_argument("--prompt", type=str, default="default", help="Specific Prompt")
    parser.add_argument("--voice_id", type=str, default="", help="Voice ID")
    parser.add_argument("--custom_generated_prompt", type=str, default="", help="Custom Generated Prompt")
    parser.add_argument("--default", action="store_true", help="Default configurations")
    parser.add_argument("--xtts", action="store_true", help="Use XTTS")
    parser.add_argument("--elevenlabs", action="store_true", help="Use ElevenLabs")
    args = parser.parse_args()
    room_url = args.room_url
    token = args.token
    
    if args.default:
        config = get_daily_config()
        room_url = config.room_url
        token = config.token

    if room_url is None:
        raise ValueError("Room URL is required")

    asyncio.run(main(room_url, token, args.xtts, args.elevenlabs, args.prompt, args.voice_id, args.custom_generated_prompt))
