# 캐스퍼 EV 보조금 신청가능 모니터

경남 김해시(또는 원하는 지자체)의 캐스퍼 일렉트릭 전기차 구매보조금이
**"임시중단/마감"** → **"신청 가능"** 으로 바뀌는 순간을 1시간 주기로 감지해서
**Discord로 알림**(`@everyone`)을 보냅니다.

> 의존성 없음 — Python 3 표준 라이브러리만 사용합니다 (`pip install` 불필요).
> 리눅스/맥/윈도우 어디서나 동일하게 동작합니다.

---

## 1. 빠른 시작

```bash
git clone https://github.com/suitable8111/casper-subsidy-monitor.git
cd casper-subsidy-monitor

# Discord 자격증명 입력 (.env — GitHub엔 안 올라감)
cp .env.example .env
nano .env            # DISCORD_WEBHOOK_URL  또는  DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID

# 1회 테스트 (현재 상태 즉시 확인 + 디스코드로 한 번 전송)
set -a; . ./.env; set +a
CASPER_NOTIFY_EACH_CHECK=1 python3 casper_subsidy_monitor.py --once
```

테스트 메시지가 디스코드에 도착하면 연동 성공입니다.

---

## 2. 24시간 상시 운영 (systemd · 권장)

서버 재부팅 후에도 자동 시작되고, 죽으면 자동 재시작됩니다.

> ⚠️ 동봉된 `casper-monitor.service`의 경로(`/opt/...`)는 예시입니다.
> 아래 명령은 **현재 폴더/계정/python 경로를 자동으로 채워** 서비스 파일을 생성하므로 경로 오류가 없습니다.
> **반드시 clone한 폴더 안에서 실행하세요.**

```bash
cd ~/casper-subsidy-monitor          # clone한 실제 위치로 이동
ls -la .env                          # .env 존재 확인 (없으면 위 1번부터)

sudo tee /etc/systemd/system/casper-monitor.service >/dev/null <<EOF
[Unit]
Description=Casper EV Subsidy Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
EnvironmentFile=$(pwd)/.env
ExecStart=$(which python3) $(pwd)/casper_subsidy_monitor.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now casper-monitor
systemctl status casper-monitor --no-pager -l     # Active: active (running) 확인
```

> 실전 서비스에는 `CASPER_NOTIFY_EACH_CHECK`를 **넣지 마세요.**
> 넣으면 1시간마다 "아직 마감" 메시지가 계속 옵니다.
> 빼면 평소엔 조용하다가 **마감→가능 전환 시 딱 한 번**만 알림이 갑니다.

### 간단 버전 (재부팅 자동시작 불필요 시)
```bash
set -a; . ./.env; set +a
nohup python3 casper_subsidy_monitor.py > casper_monitor.log 2>&1 &
```

---

## 3. 운영 명령어

```bash
# 상태 확인
systemctl status casper-monitor --no-pager

# 로그 실시간 보기 (매 시간 체크 찍힘)
journalctl -u casper-monitor -f

# 최근 로그 20줄
journalctl -u casper-monitor --no-pager | tail -20

# 코드 업데이트 후 재시작
cd ~/casper-subsidy-monitor && git pull
sudo systemctl restart casper-monitor
```

---

## 4. 종료 / 제거

### 잠깐 멈추기 (설정 유지)
```bash
sudo systemctl stop casper-monitor          # 지금 멈춤 (재부팅하면 다시 시작됨)
sudo systemctl start casper-monitor         # 다시 시작
```

### 완전히 끄기 (재부팅해도 시작 안 함)
```bash
sudo systemctl disable --now casper-monitor # 멈춤 + 자동시작 해제
```

### systemd에서 완전히 삭제
```bash
sudo systemctl disable --now casper-monitor
sudo rm /etc/systemd/system/casper-monitor.service
sudo systemctl daemon-reload
sudo systemctl reset-failed casper-monitor  # (혹시 failed 기록 남아있으면 정리)
```

### nohup으로 띄운 경우 종료
```bash
pkill -f casper_subsidy_monitor.py          # 프로세스 종료
# 또는 PID 확인 후 개별 종료:
ps aux | grep casper_subsidy_monitor.py | grep -v grep
kill <PID>
```

### 폴더까지 완전 삭제
```bash
# 위에서 서비스 삭제를 먼저 한 뒤
rm -rf ~/casper-subsidy-monitor
```

---

## 5. 동작 원리

견적 페이지가 내부적으로 호출하는 공개 API를 직접 폴링합니다 (로그인/쿠키 불필요):

```
GET https://casper.hyundai.com/gw/wp/product/v2/product/elec-subsidy/region-info
    ?regionCode=4825&receiptScnCode=E&targetUserCode=01
```

응답 예시(현재 = 마감):
```json
{ "data": {
    "finalSubsidyApplyState": "F",                 // F = 마감/중단
    "pcExposureSbc": "지자체의 다음 공모를 기다려주세요.",
    "publicNoticeCount": "1052", "receiptCount": "959"
}}
```
- `finalSubsidyApplyState != "F"` 가 되거나 문구가 "신청할 수 있어요/가능"으로 바뀌면 → **신청 가능**으로 판정하고 알림.
- `casper_monitor_state.json` 에 직전 상태를 저장 → 재시작해도 중복 알림 없이, **마감→가능 전환 순간 1회만** 알림.

> 참고: 견적 URL의 `estimationUrl=VTAwMDU4MDc2NjYz` 파라미터는 base64(`U00058076663`),
> 저장된 견적 ID일 뿐이라 모니터링에는 불필요합니다. 지역은 `regionCode`로만 결정됩니다.

---

## 6. Discord 설정 (둘 중 하나)

### 방법 A — Webhook (가장 간단, 권장)
1. Discord 채널 → 설정(톱니) → 연동 → 웹후크 → 새 웹후크 → URL 복사
2. `.env` 에 `DISCORD_WEBHOOK_URL=...` 입력

### 방법 B — Bot Token
1. https://discord.com/developers 에서 봇 생성 → 토큰 발급 → 채널에 봇 초대(메시지 보내기 권한)
2. 채널 ID 확인(개발자 모드 → 채널 우클릭 → ID 복사)
3. `.env` 에 `DISCORD_BOT_TOKEN=...` + `DISCORD_CHANNEL_ID=...` 입력

> 🔐 토큰/URL은 `.env` 파일에만 넣으세요. `.gitignore`에 의해 GitHub에 올라가지 않습니다.

---

## 7. 환경변수 옵션

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DISCORD_WEBHOOK_URL` | — | 디스코드 웹훅 URL (방법 A) |
| `DISCORD_BOT_TOKEN` | — | 봇 토큰 (방법 B) |
| `DISCORD_CHANNEL_ID` | — | 알림 채널 ID (방법 B) |
| `CASPER_REGION_CODE` | `4825` | 지자체 행정코드 (경남 김해시) |
| `CASPER_REGION_NAME` | `경남 김해시` | 알림 문구용 지역 이름 |
| `CASPER_INTERVAL_SEC` | `3600` | 폴링 주기(초) |
| `CASPER_STATE_FILE` | 스크립트 옆 | 상태 저장 파일 경로 |
| `CASPER_NOTIFY_EACH_CHECK` | `0` | `1`이면 매 체크마다 현재상태도 전송(테스트용) |

---

## 8. 다른 지역 모니터링

`.env`에서 `CASPER_REGION_CODE`만 바꾸면 됩니다.
행정코드 예: 서울특별시 `1100` · 경남 `48` · 김해시 `4825`.
정확한 시/군 코드는 견적 페이지에서 해당 지역 선택 시 호출되는
`region-info?regionCode=...` 요청에서 확인할 수 있습니다.

여러 지역을 동시에 감시하려면, 폴더를 복사하고 서비스 이름을 바꿔
(`casper-monitor-busan.service` 등) 각각 다른 `CASPER_REGION_CODE`로 띄우면 됩니다.

---

## 9. 트러블슈팅

| 증상 | 원인 / 해결 |
|------|-------------|
| `Failed to load environment files: No such file or directory` | 서비스의 `EnvironmentFile` 경로가 실제 `.env`와 다름 → 2번의 `sudo tee` 명령으로 재생성 |
| `status=resources` / `activating (auto-restart)` | 경로/계정/python 위치 불일치 → 2번 자동경로 명령 사용 |
| 디스코드 메시지 안 옴 | `journalctl -u casper-monitor`에서 `전송 실패` 확인. 웹훅 URL/봇 토큰·채널ID·봇 권한 점검 |
| 평소 메시지가 안 옴 | **정상**입니다. 마감 상태일 땐 조용하고, 가능 전환 시에만 알림 |
