"""미디어 모듈 공통 입출력 타입. 변경은 Claude Code만 한다(PRD 11장 협업 규칙)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

FetchStatus = Literal["fetched", "failed"]
ExtractionStatus = Literal["succeeded", "failed", "empty"]
Medium = Literal["audio", "screen", "caption"]


@dataclass(frozen=True)
class Limits:
    """10장 최소 운영 계약의 상한값."""

    max_video_bytes: int = 200 * 1024 * 1024
    download_timeout_s: int = 180
    ffmpeg_timeout_s: int = 300
    max_frames: int = 60
    ocr_batch_size: int = 10  # 비전 LLM 1회 호출에 넣는 프레임 수. 60장 → 6회


@dataclass
class FetchResult:
    status: FetchStatus
    video_path: Path | None = None
    method: Literal["direct", "yt-dlp"] | None = None
    error: str | None = None  # 실패 이유(사람이 읽는 짧은 코드:설명)
    caption: str | None = None  # yt-dlp 메타데이터에서 얻은 캡션(있으면)


@dataclass
class Segment:
    """audio: start/end 초. screen: start=프레임 시각, end=None."""

    start: float
    end: float | None
    text: str

    def as_json(self) -> dict:
        if self.end is None:
            return {"frame_ts": self.start, "text": self.text}
        return {"start": self.start, "end": self.end, "text": self.text}


@dataclass
class ExtractionResult:
    medium: Medium
    status: ExtractionStatus
    extractor_version: str
    text: str = ""
    segments: list[Segment] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class Frame:
    ts: float
    path: Path


class Transcriber(Protocol):
    """오디오 파일 → 구간 목록."""

    version: str

    def transcribe(self, audio_path: Path) -> list[Segment]: ...


class VisionReader(Protocol):
    """프레임 묶음 → 프레임별 화면 글자(입력과 같은 순서·같은 개수, 글자 없으면 빈 문자열).

    한 번의 모델 호출로 여러 프레임을 읽는다. 개수가 맞지 않는 응답은 예외로 알린다.
    """

    version: str

    def read_batch(self, frames: list[Frame]) -> list[str]: ...
