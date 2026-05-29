"""Streaming speech-to-text helpers for Hermes voice mode.

The existing voice path records a bounded WAV file and transcribes it after
capture. This module is the low-latency path: microphone PCM is sent to a
streaming STT provider and transcript events are emitted while the user speaks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from hermes_cli.config import get_env_value, load_config

logger = logging.getLogger(__name__)


TranscriptCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]


@dataclass(frozen=True)
class DeepgramStreamingConfig:
    api_key: str
    model: str = "nova-3"
    language: str = "ja"
    sample_rate: int = 16000
    channels: int = 1
    interim_results: bool = True
    smart_format: bool = True
    endpointing: int = 300
    vad_events: bool = True
    chunk_ms: int = 100
    url: str = "wss://api.deepgram.com/v1/listen"


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    is_final: bool
    speech_final: bool = False


TranscriptEventCallback = Callable[[TranscriptEvent], None]


def transcript_event_to_json(event: TranscriptEvent) -> dict[str, Any]:
    return {
        "text": event.text,
        "is_final": event.is_final,
        "speech_final": event.speech_final,
    }


def iter_wav_pcm_chunks(
    path: str | Path,
    *,
    sample_rate: int,
    channels: int,
    chunk_ms: int,
) -> Any:
    """Yield PCM16 chunks from a WAV file matching Deepgram streaming settings."""
    path = Path(path)
    with wave.open(str(path), "rb") as wav:
        actual_channels = wav.getnchannels()
        actual_sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        compression = wav.getcomptype()
        if compression != "NONE":
            raise ValueError(f"{path} must be an uncompressed PCM WAV file")
        if sample_width != 2:
            raise ValueError(f"{path} must be 16-bit PCM; got sample width {sample_width}")
        if actual_channels != channels:
            raise ValueError(f"{path} has {actual_channels} channel(s); expected {channels}")
        if actual_sample_rate != sample_rate:
            raise ValueError(f"{path} has {actual_sample_rate} Hz; expected {sample_rate} Hz")

        frames_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
        while True:
            chunk = wav.readframes(frames_per_chunk)
            if not chunk:
                break
            yield chunk


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value: Any, default: int, *, minimum: int = 1) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def load_deepgram_streaming_config(config: Optional[dict[str, Any]] = None) -> DeepgramStreamingConfig:
    root = config if isinstance(config, dict) else load_config()
    streaming = root.get("streaming_stt") if isinstance(root, dict) else None
    streaming = streaming if isinstance(streaming, dict) else {}
    dg = streaming.get("deepgram")
    dg = dg if isinstance(dg, dict) else {}

    api_key = str(dg.get("api_key") or get_env_value("DEEPGRAM_API_KEY") or "").strip()
    return DeepgramStreamingConfig(
        api_key=api_key,
        model=str(dg.get("model") or "nova-3"),
        language=str(dg.get("language") or "ja"),
        sample_rate=_as_int(dg.get("sample_rate"), 16000, minimum=8000),
        channels=_as_int(dg.get("channels"), 1, minimum=1),
        interim_results=_as_bool(dg.get("interim_results"), True),
        smart_format=_as_bool(dg.get("smart_format"), True),
        endpointing=_as_int(dg.get("endpointing"), 300, minimum=0),
        vad_events=_as_bool(dg.get("vad_events"), True),
        chunk_ms=_as_int(dg.get("chunk_ms"), 100, minimum=20),
        url=str(dg.get("url") or "wss://api.deepgram.com/v1/listen"),
    )


def build_deepgram_listen_url(config: DeepgramStreamingConfig) -> str:
    params: dict[str, str | int] = {
        "model": config.model,
        "language": config.language,
        "encoding": "linear16",
        "sample_rate": config.sample_rate,
        "channels": config.channels,
        "interim_results": str(config.interim_results).lower(),
        "smart_format": str(config.smart_format).lower(),
        "endpointing": config.endpointing,
        "vad_events": str(config.vad_events).lower(),
    }
    return f"{config.url}?{urlencode(params)}"


def _default_ssl_context() -> ssl.SSLContext:
    """Use certifi when available so framework Python on macOS has CA roots."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def parse_deepgram_message(message: str | bytes) -> Optional[TranscriptEvent]:
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return None

    if payload.get("type") != "Results":
        return None

    alternatives = (
        payload.get("channel", {}).get("alternatives", [])
        if isinstance(payload.get("channel"), dict)
        else []
    )
    if not alternatives or not isinstance(alternatives[0], dict):
        return None

    text = str(alternatives[0].get("transcript") or "").strip()
    if not text:
        return None

    return TranscriptEvent(
        text=text,
        is_final=bool(payload.get("is_final")),
        speech_final=bool(payload.get("speech_final")),
    )


class DeepgramStreamingSession:
    """Background microphone-to-Deepgram streaming session."""

    def __init__(
        self,
        config: DeepgramStreamingConfig,
        *,
        on_partial: Optional[TranscriptCallback] = None,
        on_final: Optional[TranscriptCallback] = None,
        on_event: Optional[TranscriptEventCallback] = None,
        on_status: Optional[StatusCallback] = None,
    ) -> None:
        if not config.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is required for streaming STT")
        self.config = config
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_event = on_event
        self.on_status = on_status
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._audio_queue: Optional[asyncio.Queue[Optional[bytes]]] = None
        self._started = threading.Event()
        self._closed = threading.Event()
        self._startup_error: Optional[BaseException] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("streaming STT session is already running")
        self._thread = threading.Thread(target=self._run_thread, name="hermes-deepgram-stt", daemon=True)
        self._thread.start()
        self._started.wait(timeout=10)
        if self._startup_error:
            raise RuntimeError(f"streaming STT failed to start: {self._startup_error}") from self._startup_error
        if not self._started.is_set():
            raise RuntimeError("streaming STT failed to start within 10 seconds")

    def stop(self, timeout: float = 10.0) -> None:
        logger.info("Deepgram streaming STT stop requested")
        queue = self._audio_queue
        loop = self._loop
        if queue is not None and loop is not None and loop.is_running():
            loop.call_soon_threadsafe(queue.put_nowait, None)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._closed.set()
        logger.info("Deepgram streaming STT stop completed")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _emit_status(self, status: str) -> None:
        if self.on_status:
            self.on_status(status)

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run())
        except BaseException as exc:
            self._startup_error = exc
            self._started.set()
            logger.warning("Deepgram streaming STT session failed: %s", exc, exc_info=True)
            self._emit_status("idle")

    async def _run(self) -> None:
        try:
            import sounddevice as sd
            import websockets
        except ImportError as exc:
            raise RuntimeError("streaming STT requires sounddevice and websockets") from exc

        self._loop = asyncio.get_running_loop()
        self._audio_queue = asyncio.Queue()
        uri = build_deepgram_listen_url(self.config)
        headers = {"Authorization": f"Token {self.config.api_key}"}

        logger.info(
            "Deepgram streaming STT connecting: model=%s language=%s sample_rate=%s chunk_ms=%s",
            self.config.model,
            self.config.language,
            self.config.sample_rate,
            self.config.chunk_ms,
        )
        async with websockets.connect(
            uri,
            additional_headers=headers,
            ssl=_default_ssl_context(),
        ) as ws:
            logger.info("Deepgram streaming STT connected")
            blocksize = max(1, int(self.config.sample_rate * self.config.chunk_ms / 1000))

            def callback(indata: bytes, frames: int, time: Any, status: Any) -> None:
                if status:
                    logger.debug("sounddevice input status: %s", status)
                loop = self._loop
                queue = self._audio_queue
                if loop is not None and queue is not None:
                    loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

            self._emit_status("listening")
            self._started.set()
            logger.info("Deepgram streaming STT listening")
            with sd.RawInputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype="int16",
                blocksize=blocksize,
                callback=callback,
            ):
                sender = asyncio.create_task(self._send_audio(ws))
                receiver = asyncio.create_task(self._receive_transcripts(ws))
                done, pending = await asyncio.wait(
                    {sender, receiver},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if receiver in done:
                    sender.cancel()
                    receiver.result()
                    return

                sender.result()
                try:
                    await asyncio.wait_for(receiver, timeout=5)
                except asyncio.TimeoutError:
                    receiver.cancel()
                for task in pending:
                    if not task.done():
                        task.cancel()

        self._emit_status("idle")
        logger.info("Deepgram streaming STT idle")

    async def _send_audio(self, ws: Any) -> None:
        assert self._audio_queue is not None
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                try:
                    await ws.send(json.dumps({"type": "CloseStream"}))
                except Exception:
                    logger.debug("failed to send Deepgram CloseStream", exc_info=True)
                return
            await ws.send(chunk)

    async def _receive_transcripts(self, ws: Any) -> None:
        async for message in ws:
            event = parse_deepgram_message(message)
            if event is None:
                continue
            if event.is_final:
                logger.info(
                    "Deepgram final transcript received (%d chars, speech_final=%s)",
                    len(event.text),
                    event.speech_final,
                )
                if self.on_event:
                    self.on_event(event)
                if self.on_final:
                    self.on_final(event.text)
            elif self.on_partial:
                self.on_partial(event.text)
