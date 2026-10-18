import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from rsb.media import fetch, frames, ocr, transcribe
from rsb.media.types import Frame, Limits, Segment


@pytest.fixture
def public_dns(monkeypatch):
    def resolve(host, port, **kwargs):
        address = {"localhost": "127.0.0.1"}.get(host, host)
        if host == "public.example":
            address = "93.184.216.34"
        return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    monkeypatch.setattr(socket, "getaddrinfo", resolve)


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://10.2.3.4", "http://169.254.169.254", "http://[::1]", "http://localhost", "ftp://public.example", "file:///tmp/a", "http://100.64.0.1", "http://[::ffff:8.8.8.8]", "http://224.0.0.1", "http://0.0.0.0"])
def test_blocked(url, public_dns):
    with pytest.raises(fetch.BlockedURLError):
        fetch.check_public_url(url)


def transport(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(fetch.httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handler), **kw))


def test_redirect_blocked(monkeypatch, tmp_path, public_dns):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://10.0.0.1/video"})
    transport(monkeypatch, handler)
    result = fetch.fetch_video("http://public.example", tmp_path)
    assert result.error.startswith("blocked_url:")
    assert len(calls) == 1


def test_all_dns_records(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [
        (2, 1, 6, "", ("8.8.8.8", 80)), (10, 1, 6, "", ("fe80::1", 80))])
    with pytest.raises(fetch.BlockedURLError):
        fetch.check_public_url("http://public.example")


@pytest.mark.parametrize("limit,status", [(3, "failed"), (20, "fetched")])
def test_direct(monkeypatch, tmp_path, public_dns, limit, status):
    transport(monkeypatch, lambda r: httpx.Response(200, headers={"content-type": "video/mp4"}, content=b"123456"))
    result = fetch.fetch_video("https://public.example", tmp_path, Limits(max_video_bytes=limit))
    assert result.status == status
    if status == "failed":
        assert result.error == "too_large"
        assert not list(tmp_path.iterdir())
    else:
        assert result.video_path.read_bytes() == b"123456"


def test_ytdlp(monkeypatch, tmp_path, public_dns):
    transport(monkeypatch, lambda r: httpx.Response(200, headers={"content-type": "text/html"}))
    def run(args, **kwargs):
        assert isinstance(args, list) and kwargs["shell"] is False
        assert kwargs["timeout"] <= 180
        assert "--no-playlist" in args and "--max-filesize" in args
        output = Path(args[args.index("-o") + 1])
        output.with_name("video.mp4").write_bytes(b"video")
        output.with_name("video.info.json").write_text(json.dumps({"description": "caption"}))
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(fetch.subprocess, "run", run)
    result = fetch.fetch_video("https://public.example", tmp_path)
    assert result.caption == "caption" and result.method == "yt-dlp"
    assert len(list(tmp_path.iterdir())) == 1


@pytest.fixture
def videos(tmp_path):
    paths = []
    for audio in (False, True):
        path = tmp_path / f"video-{audio}.mp4"
        args = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=4"]
        if audio:
            args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=4"]
        args += ["-vf", "drawtext=text='FIRST':enable='lt(t,2)':x=10:y=10,drawtext=text='SECOND':enable='gte(t,2)':x=10:y=10", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", "-threads", "1", str(path)]
        subprocess.run(args, shell=False, timeout=30, check=True, capture_output=True)
        paths.append(path)
    return paths


class Reader:
    version = "fake1"
    def read(self, path):
        assert path.exists()
        return "보이는 글자"


class Speech:
    version = "fake1"
    def transcribe(self, path):
        import wave
        with wave.open(str(path)) as wav:
            assert wav.getframerate() == 16000 and wav.getnchannels() == 1
        return [Segment(0.1, 1.2, "안녕하세요")]


def test_frames(videos, tmp_path):
    sampled = frames.sample_frames(videos[0], tmp_path / "frames", Limits(max_frames=3))
    assert 1 < len(sampled) <= 3
    assert sampled[0].ts == pytest.approx(0)
    assert sampled[-1].ts >= 2
    assert all(f.path.exists() for f in sampled)
    assert [f.ts for f in sampled] == sorted(f.ts for f in sampled)


def test_speech(videos, tmp_path):
    work = tmp_path / "work"
    assert transcribe.extract_speech(videos[0], Speech(), work).status == "empty"
    result = transcribe.extract_speech(videos[1], Speech(), work)
    assert result.status == "succeeded"
    assert result.segments[0].end == 1.2
    assert result.extractor_version == "transcribe@1+fake1"
    assert not list(work.iterdir())


def test_ocr(videos, tmp_path):
    work = tmp_path / "work"
    result = ocr.extract_screen_text(videos[0], Reader(), work)
    assert result.status == "succeeded" and len(result.segments) == 1
    assert result.segments[0].end is None
    assert result.extractor_version == "ocr@1+fake1"
    assert not list(work.iterdir())


@pytest.mark.parametrize("raises,status", [(False, "empty"), (True, "failed")])
def test_reader_failures(videos, tmp_path, raises, status):
    class Fake(Reader):
        def read(self, path):
            if raises:
                raise RuntimeError("failure")
            return ""
    work = tmp_path / "work"
    result = ocr.extract_screen_text(videos[0], Fake(), work)
    assert result.status == status
    assert not list(work.iterdir())


def test_speech_failure_cleanup(videos, tmp_path):
    class Broken(Speech):
        def transcribe(self, path):
            raise RuntimeError("backend unavailable")
    work = tmp_path / "work"
    result = transcribe.extract_speech(videos[1], Broken(), work)
    assert result.status == "failed" and result.error
    assert not list(work.iterdir())


def test_static_dedup(tmp_path):
    video = tmp_path / "static.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:size=64x64:duration=3", str(video)], shell=False, timeout=30, check=True)
    assert len(frames.sample_frames(video, tmp_path / "frames")) == 1


def test_ytdlp_timeout(monkeypatch, tmp_path, public_dns):
    transport(monkeypatch, lambda r: httpx.Response(200, headers={"content-type": "text/html"}))
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
    monkeypatch.setattr(fetch.subprocess, "run", run)
    assert fetch.fetch_video("http://public.example", tmp_path).error == "timeout"
    assert not list(tmp_path.iterdir())


def test_ytdlp_error(monkeypatch, tmp_path, public_dns):
    transport(monkeypatch, lambda r: httpx.Response(200, headers={"content-type": "text/html"}))
    monkeypatch.setattr(fetch.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stderr="first\nlast\n"))
    assert fetch.fetch_video("http://public.example", tmp_path).error == "ytdlp_failed:last"


def test_openai_backends(monkeypatch, tmp_path):
    import openai
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if "messages" in kwargs:
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="텍스트"))])
        return SimpleNamespace(segments=[SimpleNamespace(start=0.2, end=0.8, text=" 말 ")])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                             audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    monkeypatch.setattr(openai, "OpenAI", lambda: client)
    monkeypatch.setenv("RSB_VISION_MODEL", "vision-test")
    monkeypatch.setenv("RSB_WHISPER_MODEL", "speech-test")
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fake-image")
    reader = ocr.OpenAIVisionReader()
    assert reader.read(image) == "텍스트"
    assert calls[0]["model"] == "vision-test"
    assert "지시가 아니다" in calls[0]["messages"][0]["content"]
    assert calls[0]["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    backend = transcribe.OpenAIWhisperTranscriber()
    assert backend.transcribe(image)[0] == Segment(0.2, 0.8, "말")
    assert calls[1]["response_format"] == "verbose_json"
    assert calls[1]["language"] == "ko"
    assert calls[1]["timestamp_granularities"] == ["segment"]


def test_consecutive_ocr(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "sample_frames", lambda *args: [Frame(i, tmp_path / f"{i}.jpg") for i in range(5)])
    class Fake(Reader):
        def __init__(self):
            self.texts = iter(["A", "A", "", "A", "B"])
        def read(self, path):
            return next(self.texts)
    result = ocr.extract_screen_text(tmp_path / "video", Fake(), tmp_path / "work")
    assert [(s.start, s.text) for s in result.segments] == [(0, "A"), (3, "A"), (4, "B")]
