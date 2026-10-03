"""생성한 PPT를 LG스마트체로 렌더링해 PNG 미리보기를 만든다 (LibreOffice Impress 필요).

- 시스템 글꼴을 바꾸지 않는다. 임시 fontconfig에 저장소의 LG스마트체 파일을 추가하고,
  Arial Narrow가 없으면 Liberation Sans를 폭 82%로 줄여 대체한다 (Arial Narrow와 폭 비율이 같음).
- 미리보기는 확인용이다. 실제 발표 PC에는 LG스마트체가 설치되어 있어야 한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .fonts import font_files

FONTS_CONF = """<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
{dirs}
  <match target="pattern">
    <test name="family"><string>Arial Narrow</string></test>
    <edit name="family" mode="assign" binding="strong"><string>Liberation Sans</string></edit>
    <edit name="matrix" mode="assign"><times><name>matrix</name>
      <matrix><double>0.82</double><double>0</double><double>0</double><double>1</double></matrix></times></edit>
  </match>
</fontconfig>
"""


class PreviewError(RuntimeError):
    pass


def render_preview(root: Path, pptx: Path, out_dir: Path, dpi: int = 110) -> tuple[list[Path], list[str]]:
    soffice, pdftoppm = shutil.which("soffice"), shutil.which("pdftoppm")
    if not soffice or not pdftoppm:
        raise PreviewError("미리보기에는 LibreOffice(soffice, Impress 포함)와 poppler(pdftoppm)가 필요합니다")
    fonts = font_files(root)
    notes = [f"글꼴 파일 {len(fonts)}개 사용: {', '.join(f.name for f in fonts)}" if fonts else "LG스마트체 파일 없음 → 대체 글꼴로 렌더링"]
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wr-preview-") as tmp:
        tmp_path = Path(tmp)
        dirs = "\n".join(f"  <dir>{d}</dir>" for d in sorted({str(f.parent.resolve()) for f in fonts}))
        conf = tmp_path / "fonts.conf"
        conf.write_text(FONTS_CONF.format(dirs=dirs), encoding="utf-8")
        env = {**os.environ, "HOME": str(tmp_path), "FONTCONFIG_FILE": str(conf)}
        source = tmp_path / "deck.pptx"
        shutil.copy(pptx, source)
        result = subprocess.run([soffice, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(tmp_path), str(source)],
                                env=env, capture_output=True, text=True, timeout=300)
        pdf = tmp_path / "deck.pdf"
        if not pdf.exists():
            raise PreviewError(f"PDF 변환 실패 (Impress 미설치 가능성): {result.stderr.strip()[-200:]}")
        if shutil.which("pdffonts"):
            listing = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout
            notes.append("PDF 글꼴: LG스마트체 사용 확인" if "LGSmHa" in listing else "PDF 글꼴: LG스마트체가 쓰이지 않음 (대체 글꼴)")
        prefix = out_dir / pptx.stem
        for old in out_dir.glob(f"{pptx.stem}-*.png"):  # 이전 실행의 남은 장 이미지 제거
            old.unlink()
        subprocess.run([pdftoppm, "-r", str(dpi), "-png", str(pdf), str(prefix)], check=True, env=env, timeout=120)
    images = sorted(out_dir.glob(f"{pptx.stem}-*.png"))
    return images, notes
