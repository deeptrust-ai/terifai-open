import aiohttp
import io
import os
import time
import wave
from dataclasses import dataclass

from modal import Function, functions
from pipecat.frames.frames import (
    Frame,
    AudioRawFrame,
    CancelFrame,
    DataFrame,
    EndFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.utils.audio import calculate_audio_volume, exp_smoothing

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
DEFAULT_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID")
MIN_SECS_TO_LAUNCH = 30
DEFAULT_POLL_INTERVAL_SECS = 5
logger.info(f"Default voice ID: {DEFAULT_VOICE_ID}")


@dataclass
class AudioFrameTerrify(DataFrame):
    """A chunk of audio. Will be played by the transport if the transport's
    microphone has been enabled.

    """

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


class TerrifyAudioCapture(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, AudioRawFrame):
            audio_capture_frame = AudioFrameTerrify(
                audio=frame.audio,
                sample_rate=frame.sample_rate,
                num_frames=frame.num_frames,
            )
            logger.debug(f"HERE Audio capture frame: {audio_capture_frame}")
            await self.push_frame(audio_capture_frame, direction)

        logger.debug(f"HERE Pushing frame: {frame}")
        await self.push_frame(frame, direction)


class DeepgramTerrify(DeepgramSTTService):
    def __init__(self):
        super().__init__(api_key=DEEPGRAM_API_KEY)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
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
        """Collects audio frames"""
        volume = self._get_smoothed_volume(frame)
        if volume >= self._min_volume:
            # If volume is high enough, write new data to wave file
            self._wave.writeframes(frame.audio)
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

    async def _launch_clone_job(self, audio_data: bytes):
        """Launches a clone job with the given audio data"""
        add_elevenlabs_voice = Function.lookup(
            "terifai-functions", "add_elevenlabs_voice"
        )
        job = add_elevenlabs_voice.spawn(audio_data)
        self._job_id = job.object_id
        logger.debug(f"Voice cloning job launch: {self._job_id}")

    def _poll_job(self):
        """Polls the status of a job"""
        self._last_poll_time = time.time()
        logger.debug(f"Polling job: {self._job_id}")
        function_call = functions.FunctionCall.from_id(self._job_id)
        try:
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

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Processes a frame of audio data"""
        await super().process_frame(frame, direction)

        if isinstance(frame, CancelFrame) or isinstance(frame, EndFrame):
            self._wave.close()
            await self.push_frame(frame, direction)
        elif isinstance(frame, AudioFrameTerrify):
            await self._write_audio_frames(frame)
            await self.push_frame(frame, direction)
