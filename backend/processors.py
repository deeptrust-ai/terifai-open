import io
import os
import time
import wave
from dataclasses import dataclass
from typing import List, Dict

import aiohttp
import requests
from dotenv import load_dotenv
from loguru import logger
from modal import Cls, Function, functions
from pipecat.audio.utils import calculate_audio_volume, exp_smoothing
from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    DataFrame,
    EndFrame,
    Frame,
    LLMMessagesAppendFrame,
    LLMMessagesUpdateFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.services.xtts import XTTSService

from backend.prompts import (
    LLM_VOICE_CHANGE_PROMPT_DEFAULT,
    LLM_VOICE_CHANGE_PROMPT_IT_SUPPORT, 
    LLM_VOICE_CHANGE_PROMPT_CORPORATE,
    LLM_VOICE_CHANGE_PROMPT_FINANCE_FRAUD,
    LLM_VOICE_CHANGE_PROMPT_ENGINEERING_BREACH,
    LLM_VOICE_CHANGE_PROMPT_SECURITY_ALERT,
    transition_line
)

load_dotenv()

DEFAULT_CARTESIA_VOICE_ID = "e00d0e4c-a5c8-443f-a8a3-473eb9a62355"

# api keys
CARTESIA_API_KEY = os.environ.get("CARTESIA_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
DEFAULT_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID")

# voice change prompt map
PROMPT_MAP = {
    "default": LLM_VOICE_CHANGE_PROMPT_DEFAULT,
    "it_support": LLM_VOICE_CHANGE_PROMPT_IT_SUPPORT,
    "corporate": LLM_VOICE_CHANGE_PROMPT_CORPORATE,
    "finance_fraud": LLM_VOICE_CHANGE_PROMPT_FINANCE_FRAUD,
    "engineering_breach": LLM_VOICE_CHANGE_PROMPT_ENGINEERING_BREACH,
    "security_alert": LLM_VOICE_CHANGE_PROMPT_SECURITY_ALERT,

}

# settings
MIN_SECS_TO_LAUNCH = int(os.environ.get("MIN_SECS_TO_LAUNCH", 30))
DEFAULT_POLL_INTERVAL_SECS = 5
logger.info(f"Default voice ID: {DEFAULT_VOICE_ID}")


@dataclass
class AudioFrameTerrify(DataFrame):
    """Seperate dataclass for audio frames to be processed by the TerifAI custom Deepgram and ElevenLabs services."""

    audio: bytes
    sample_rate: int
    num_channels: int

    def __post_init__(self):
        super().__post_init__()
        self.num_frames = int(len(self.audio) / (self.num_channels * 2))

    def __str__(self):
        return f"{self.name}(size: {len(self.audio)}, frames: {self.num_frames}, sample_rate: {self.sample_rate}, channels: {self.num_channels})"


class TranscriptionLogger(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            logger.debug(f"Transcription: {frame.text}")

        await self.push_frame(frame)


class DeepgramTerrify(DeepgramSTTService):
    def __init__(self):
        super().__init__(api_key=DEEPGRAM_API_KEY)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Processes a frame of audio data via AudioFrameTerrify because STT does not push AudioRawFrames downstream after transcription."""
        if isinstance(frame, AudioRawFrame):
            audio_capture_frame = AudioFrameTerrify(
                audio=frame.audio,
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
            )
            await self.push_frame(audio_capture_frame, direction)

        await super().process_frame(frame, direction)


class ElevenLabsTerrify(ElevenLabsTTSService):
    def __init__(
        self,
        *,
        aiohttp_session: aiohttp.ClientSession,
        api_key: str,
        model: str = "eleven_turbo_v2",
        **kwargs,
    ):
        super().__init__(
            aiohttp_session=aiohttp_session,
            api_key=api_key,
            model=model,
            voice_id=DEFAULT_VOICE_ID,
            **kwargs,
        )

        self._api_key = api_key

        # voice data collection attributes
        self._num_channels = 1
        self._sample_rate = 16000
        self._prev_volume = 0.0
        self._smoothing_factor = 0.2
        self._max_silence_secs = 0.3
        self._silence_frame_count = 0
        self._min_volume = 0.6
        (self._content, self._wave) = self._new_wave()

        # voice clone job attributes
        self._job_id = None
        self._job_completed = False
        self._last_poll_time = time.time()
        self._poll_interval = DEFAULT_POLL_INTERVAL_SECS

    def set_voice_id(self, voice_id: str):
        logger.debug(f"Setting voice ID: {voice_id}")
        self._voice_id = voice_id

    def get_voice_id(self):
        return self._voice_id

    def _new_wave(self):
        content = io.BytesIO()
        ww = wave.open(content, "wb")
        ww.setsampwidth(2)
        ww.setnchannels(self._num_channels)
        ww.setframerate(self._sample_rate)
        return (content, ww)

    def _get_smoothed_volume(self, frame: AudioFrameTerrify) -> float:
        volume = calculate_audio_volume(frame.audio, frame.sample_rate)
        return exp_smoothing(volume, self._prev_volume, self._smoothing_factor)

    async def _write_audio_frames(self, frame: AudioFrameTerrify):
        """Collects audio frames, and launches and polls audio frame jobs"""
        volume = self._get_smoothed_volume(frame)
        if volume >= self._min_volume:
            # If volume is high enough, write new data to wave file
            if self._wave is not None:
                try:
                    self._wave.writeframes(frame.audio)
                except Exception as e:
                    logger.error(f"Error writing audio frame: {e}")
            else:
                logger.error("Wave object is None, cannot write frames")
            self._silence_frame_count = 0
        else:
            self._silence_frame_count += frame.num_frames
        self._prev_volume = volume

        # Check if the audio length is >= 30 seconds
        audio_len_in_seconds = self._wave.getnframes() / self._sample_rate

        # Uncomment to log every 2 seconds
        # if round(audio_len_in_seconds) % 2 == 0:
        #     logger.debug(
        #         f"Audio length in seconds: {audio_len_in_seconds}/{MIN_SECS_TO_LAUNCH}"
        #     )

        if not self._job_completed:
            if audio_len_in_seconds >= MIN_SECS_TO_LAUNCH:
                self._wave.close()
                self._content.seek(0)
                await self._launch_clone_job(self._content.read())
                (self._content, self._wave) = self._new_wave()
            elif (
                self._job_id
                and (time.time() - self._last_poll_time) >= self._poll_interval
            ):
                self._poll_job()

    async def _launch_clone_job(self, audio_data: bytes):
        """Launches a clone job with the given audio data"""
        try:
            add_elevenlabs_voice = Function.lookup(
                "terifai-functions", "add_elevenlabs_voice"
            )
            job = add_elevenlabs_voice.spawn(audio_data)
            self._job_id = job.object_id
            logger.debug(f"Voice cloning job launch: {self._job_id}")
        except Exception as e:
            logger.error(f"Error launching voice cloning job: {e}")

    def _poll_job(self):
        """Polls the status of a job"""
        logger.debug(f"Polling job: {self._job_id}")
        self._last_poll_time = time.time()
        try:
            function_call = functions.FunctionCall.from_id(self._job_id)
            result = function_call.get(timeout=0)
        except TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error polling job: {e}")
            return None

        logger.debug(f"Job completed: {result}")
        self._job_completed = True
        self.set_voice_id(result)
        return result

    def _delete_clone(self):
        """Deletes voice clone"""
        if not self._job_completed and not self._voice_id:
            return

        try:
            url = f"https://api.elevenlabs.io/v1/voices/{self._voice_id}"
            headers = {"xi-api-key": self._api_key}
            response = requests.request("DELETE", url, headers=headers)
            response.raise_for_status()
            logger.info(f"Deleted voice clone: {self._voice_id}")
        except Exception as e:
            logger.error(f"Error deleting voice clone: {e}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Processes a frame of audio data"""
        await super().process_frame(frame, direction)

        if isinstance(frame, CancelFrame) or isinstance(frame, EndFrame):
            self._wave.close()
            self._delete_clone()
            await self.push_frame(frame, direction)
        elif isinstance(frame, AudioFrameTerrify):
            await self._write_audio_frames(frame)
            await self.push_frame(frame, direction)


class XTTSTerrify(XTTSService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.info("XTTSTerrify initialized")
        logger.info(f"Speakers: {self._studio_speakers.keys()}")
        logger.info(f"Using XTTS voice: {self._voice_id}")

        # voice data collection attributes
        self._num_channels = 1
        self._sample_rate = 16000
        self._prev_volume = 0.0
        self._smoothing_factor = 0.2
        self._max_silence_secs = 0.3
        self._silence_frame_count = 0
        self._min_volume = 0.6
        (self._content, self._wave) = self._new_wave()

        # voice clone job attributes
        self._job_id = None
        self._job_completed = False
        self._last_poll_time = time.time()
        self._poll_interval = DEFAULT_POLL_INTERVAL_SECS

    def set_voice_id(self, voice_id: str):
        logger.debug(f"Setting voice ID: {voice_id}")
        self._voice_id = voice_id

    def get_voice_id(self):
        return self._voice_id

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Processes a frame of audio data"""
        await super().process_frame(frame, direction)

        if isinstance(frame, CancelFrame) or isinstance(frame, EndFrame):
            self._wave.close()
            self._delete_clone()
            await self.push_frame(frame, direction)
        elif isinstance(frame, AudioFrameTerrify):
            await self._write_audio_frames(frame)
            await self.push_frame(frame, direction)

    def _new_wave(self):
        content = io.BytesIO()
        ww = wave.open(content, "wb")
        ww.setsampwidth(2)
        ww.setnchannels(self._num_channels)
        ww.setframerate(self._sample_rate)
        return (content, ww)

    async def _write_audio_frames(self, frame: AudioFrameTerrify):
        """Collects audio frames, and launches and polls audio frame jobs"""
        volume = self._get_smoothed_volume(frame)
        if volume >= self._min_volume:
            # If volume is high enough, write new data to wave file
            if self._wave is not None:
                try:
                    self._wave.writeframes(frame.audio)
                except Exception as e:
                    logger.error(f"Error writing audio frame: {e}")
            else:
                logger.error("Wave object is None, cannot write frames")
            self._silence_frame_count = 0
        else:
            self._silence_frame_count += frame.num_frames
        self._prev_volume = volume

        # Check if the audio length is >= 30 seconds
        audio_len_in_seconds = self._wave.getnframes() / self._sample_rate
        if not self._job_completed:
            if audio_len_in_seconds >= MIN_SECS_TO_LAUNCH:
                self._wave.close()
                self._content.seek(0)
                await self._launch_clone_job(self._content.read())
                (self._content, self._wave) = self._new_wave()
            elif (
                self._job_id
                and (time.time() - self._last_poll_time) >= self._poll_interval
            ):
                self._poll_job()

    def _get_smoothed_volume(self, frame: AudioFrameTerrify) -> float:
        volume = calculate_audio_volume(frame.audio, frame.sample_rate)
        return exp_smoothing(volume, self._prev_volume, self._smoothing_factor)

    async def _launch_clone_job(self, audio_data: bytes):
        """Launches a clone job with the given audio data"""
        try:
            RemoteXTTS = Cls.lookup("xtts", "XTTS")
            rxtts = RemoteXTTS()
            job = rxtts.clone_speaker.spawn(audio_data)
            self._job_id = job.object_id
            logger.debug(f"Voice cloning job launch: {self._job_id}")
        except Exception as e:
            logger.error(f"Error launching voice cloning job: {e}")

    def _poll_job(self):
        """Polls the status of a job"""
        logger.debug(f"Polling job: {self._job_id}")
        self._last_poll_time = time.time()
        try:
            function_call = functions.FunctionCall.from_id(self._job_id)
            result = function_call.get(timeout=0)
        except TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error polling job: {e}")
            return None

        logger.debug(f"Job completed: {result}")
        self._job_completed = True
        self._studio_speakers["custom"] = result
        self.set_voice_id("custom")
        return result


class CartesiaTerrify(CartesiaTTSService):
    def __init__(
        self,
        api_key: str = CARTESIA_API_KEY,
        voice_id=None,
        selected_prompt=None,
        *args,
        **kwargs,
    ):
        
        # Use DEFAULT_CARTESIA_VOICE_ID if voice_id is empty
        voice_id = voice_id if voice_id else DEFAULT_CARTESIA_VOICE_ID
        super().__init__(api_key=api_key, voice_id=voice_id, *args, **kwargs)
        
        # voice data collection attributes
        self._num_channels = 1
        self._sample_rate = 16000
        self._prev_volume = 0.0
        self._smoothing_factor = 0.2
        self._max_silence_secs = 0.3
        self._silence_frame_count = 0
        self._min_volume = 0.6
        (self._content, self._wave) = self._new_wave()

        # voice clone job attributes
        self._job_id = None
        self._job_completed = False
        self._last_poll_time = time.time()
        self._poll_interval = DEFAULT_POLL_INTERVAL_SECS

        # custom prompt
        self.selected_prompt = selected_prompt

        logger.info("CartesiaTerrify initialized")

    def set_voice_id(self, voice_id: str):
        logger.debug(f"Setting voice ID: {voice_id}")
        self._voice_id = voice_id

    def get_voice_id(self):
        return self._voice_id

    def _new_wave(self):
        content = io.BytesIO()
        ww = wave.open(content, "wb")
        ww.setsampwidth(2)
        ww.setnchannels(self._num_channels)
        ww.setframerate(self._sample_rate)
        return (content, ww)

    def _get_smoothed_volume(self, frame: AudioFrameTerrify) -> float:
        volume = calculate_audio_volume(frame.audio, frame.sample_rate)
        return exp_smoothing(volume, self._prev_volume, self._smoothing_factor)

    async def _write_audio_frames(self, frame: AudioFrameTerrify):
        """Collects audio frames, and launches and polls audio frame jobs"""
        volume = self._get_smoothed_volume(frame)
        if volume >= self._min_volume:
            # If volume is high enough, write new data to wave file
            if self._wave is not None:
                try:
                    self._wave.writeframes(frame.audio)
                except Exception as e:
                    logger.error(f"Error writing audio frame: {e}")
            else:
                logger.error("Wave object is None, cannot write frames")
            self._silence_frame_count = 0
        else:
            self._silence_frame_count += frame.num_frames
        self._prev_volume = volume

        # Check if the audio length is >= 30 seconds
        audio_len_in_seconds = self._wave.getnframes() / self._sample_rate

        # Uncomment to log every 2 seconds
        # if round(audio_len_in_seconds) % 2 == 0:
        #     logger.debug(
        #         f"Audio length in seconds: {audio_len_in_seconds}/{MIN_SECS_TO_LAUNCH}"
        #     )

        if not self._job_completed:
            if audio_len_in_seconds >= MIN_SECS_TO_LAUNCH:
                self._wave.close()
                self._content.seek(0)
                await self._launch_clone_job(self._content.read())
                (self._content, self._wave) = self._new_wave()
            elif self._job_id and (time.time() - self._last_poll_time) >= self._poll_interval:
                result = self._poll_job()
                if result:
                    if self.selected_prompt == 'default':
                        new_prompt = {"role": "system", "content": PROMPT_MAP[self.selected_prompt]}
                    else:
                        new_prompt = {"role": "system", "content": PROMPT_MAP[self.selected_prompt] + transition_line}
                    await self.push_frame(LLMMessagesUpdateFrame([new_prompt]), FrameDirection.DOWNSTREAM)

    async def _launch_clone_job(self, audio_data: bytes):
        """Launches a clone job with the given audio data"""
        try:
            add_cartesia_voice = Function.lookup(
                "terifai-functions", "add_cartesia_voice"
            )
            job = add_cartesia_voice.spawn(audio_data)
            self._job_id = job.object_id
            logger.debug(f"Voice cloning job launch: {self._job_id}")
        except Exception as e:
            logger.error(f"Error launching voice cloning job: {e}")

    def _poll_job(self):
        """Polls the status of a job"""
        logger.debug(f"Polling job: {self._job_id}")
        self._last_poll_time = time.time()
        try:
            function_call = functions.FunctionCall.from_id(self._job_id)
            result = function_call.get(timeout=0)
        except TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error polling job: {e}")
            return None

        logger.debug(f"Job completed: {result}")
        self._job_completed = True
        self.set_voice_id(result)
        return result

    def _delete_clone(self):
        """Deletes voice clone"""
        
        # If the voice is the default voice and voice was not stolen, do not delete
        if self._voice_id == DEFAULT_CARTESIA_VOICE_ID and not self._job_completed:
            return

        # If the voice is the default voice and job was completed dont delete it
        if self._voice_id == DEFAULT_CARTESIA_VOICE_ID:
            return
        
        try:
            url = f"https://api.cartesia.ai/voices/{self._voice_id}"
            headers = {"X-API-Key": self._api_key, "Cartesia-Version": "2024-06-10"}
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            logger.info(f"Deleted voice clone: {self._voice_id}")
        except Exception as e:
            logger.error(f"Error deleting voice clone: {e}")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Processes a frame of audio data"""
        await super().process_frame(frame, direction)

        if isinstance(frame, CancelFrame) or isinstance(frame, EndFrame):
            self._wave.close()
            self._delete_clone()
            await self.push_frame(frame, direction)
        elif isinstance(frame, AudioFrameTerrify):
            if self._voice_id == DEFAULT_CARTESIA_VOICE_ID:
                await self._write_audio_frames(frame)
            await self.push_frame(frame, direction)
