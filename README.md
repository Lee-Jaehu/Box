# 왜?의 끝까지 #2 — 0으로 나누면 왜 안 될까? (최종 원본)

원본 `ep02_0으로나누기.mp4` (1920×1080, H.264/AAC, 30fps, 7:14, 279,279,192 bytes)를
재인코딩 없이 바이트 그대로 3조각으로 나눈 것입니다 (GitHub 파일당 100MB 제한).

SHA-256: `20d9f6a9b32d3445447864f3b1b632f45aeacc782783335f41c9a78e18e3c674`

## 합치기
조각 3개(`ep02_master.mp4.part00`, `part01`, `part02`)를 같은 폴더에 받은 뒤:

- Windows (명령 프롬프트 cmd):
  `copy /b ep02_master.mp4.part00+ep02_master.mp4.part01+ep02_master.mp4.part02 ep02_0으로나누기.mp4`
  확인: `certutil -hashfile ep02_0으로나누기.mp4 SHA256`
- macOS / Linux:
  `cat ep02_master.mp4.part00 ep02_master.mp4.part01 ep02_master.mp4.part02 > ep02_0으로나누기.mp4`
  확인: `shasum -a 256 ep02_0으로나누기.mp4`

해시가 위 값과 같으면 원본과 똑같은 파일입니다.
전달용 브랜치이므로 받은 뒤 삭제해도 됩니다.
