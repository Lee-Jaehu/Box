"""Audio extraction and interchangeable speech backends."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .types import ExtractionResult, Limits, Segment, Transcriber


class OpenAIWhisperTranscriber:
    def __init__(self):
        from openai import OpenAI
        self.model = os.environ.get("RSB_WHISPER_MODEL", "whisper-1")
        self.version = f"openai:{self.model}"
        self.client = OpenAI()

    def transcribe(self, audio_path: Path) -> list[Segment]:
        with audio_path.open("rb") as audio:
            result = self.client.audio.transcriptions.create(
                model=self.model, file=audio, response_format="verbose_json", language="ko",
                timestamp_granularities=["segment"],
            )
        return [Segment(s.start, s.end, s.text.strip()) for s in (result.segments or []) if s.text.strip()]


class FasterWhisperTranscriber:
    def __init__(self, model: str = "small", **kwargs):
        self.model = model
        self.kwargs = kwargs
        self.version = f"faster-whisper:{model}"
        self._backend = None

    def transcribe(self, audio_path: Path) -> list[Segment]:
        if self._backend is None:
            from faster_whisper import WhisperModel
            self._backend = WhisperModel(self.model, **self.kwargs)
        segments, _ = self._backend.transcribe(str(audio_path), language="ko")
        return [Segment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]


def extract_speech(video_path: Path, transcriber: Transcriber, work_dir: Path, limits: Limits = Limits()) -> ExtractionResult:
    version = f"transcribe@1+{transcriber.version}"
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json", str(video_path.resolve())],
            shell=False, timeout=limits.ffmpeg_timeout_s, capture_output=True, text=True, check=True,
        )
        if not json.loads(probe.stdout).get("streams"):
            return ExtractionResult("audio", "empty", version)
        work_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="audio-", dir=work_dir) as temp:
            audio = Path(temp) / "audio.wav"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(video_path.resolve()), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
                shell=False, timeout=limits.ffmpeg_timeout_s, capture_output=True, check=True,
            )
            segments = [s for s in transcriber.transcribe(audio) if s.text.strip()]
            return ExtractionResult("audio", "succeeded" if segments else "empty", version,
                                    "\n".join(s.text for s in segments), segments)
    except Exception as exc:
        return ExtractionResult("audio", "failed", version, error=f"transcribe_failed:{type(exc).__name__}")
