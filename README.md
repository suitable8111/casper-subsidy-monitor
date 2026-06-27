# 캐스퍼 EV 보조금 신청가능 모니터

경남 김해시(또는 원하는 지자체)의 캐스퍼 일렉트릭 전기차 구매보조금이
**"임시중단/마감"** → **"신청 가능"** 으로 바뀌는 순간을 1시간 주기로 감지해서
**Discord로 알림**을 보냅니다.

> 의존성 없음 — Python 3 표준 라이브러리만 사용합니다 (`pip install` 불필요).
> 리눅스/맥/윈도우 어디서나 동일하게 동작합니다.

## 빠른 시작 (리눅스 서버)

```bash
git clone <your-repo-url> casper-subsidy-monitor
cd casper-subsidy-monitor

cp .env.example .env
nano .env                 # DISCORD_WEBHOOK_URL 입력

# .env 를 읽어서 1회 테스트
set -a; . ./.env; set +a
python3 casper_subsidy_monitor.py --once

# 백그라운드 상시 실행
nohup python3 casper_subsidy_monitor.py > casper_monitor.log 2>&1 &
```

서버 재부팅 후에도 자동 실행되게 하려면 동봉된 **`casper-monitor.service`** (systemd) 를 쓰세요.
파일 상단 주석에 설치 방법이 있고, 요약하면:

```bash
sudo cp casper-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now casper-monitor
journalctl -u casper-monitor -f      # 로그 실시간 확인
```

> `set -a; . ./.env; set +a` 는 `.env` 의 값을 현재 셸 환경변수로 올리는 명령입니다.
> systemd 는 `EnvironmentFile=.env` 로 자동 처리하므로 따로 source 할 필요 없습니다.

## 동작 원리

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

## Discord 설정 (둘 중 하나)

### 방법 A — Webhook (가장 간단, 권장)
1. Discord 채널 → 설정(톱니) → 연동 → 웹후크 → 새 웹후크 → URL 복사
2. 실행 시 `DISCORD_WEBHOOK_URL` 환경변수로 전달

### 방법 B — Bot Token
1. https://discord.com/developers 에서 봇 생성 → 토큰 발급 → 채널에 봇 초대(메시지 보내기 권한)
2. 알림 보낼 채널 ID 확인(개발자 모드 → 채널 우클릭 → ID 복사)
3. `DISCORD_BOT_TOKEN` + `DISCORD_CHANNEL_ID` 환경변수로 전달

> 🔐 토큰/URL은 채팅에 붙여넣지 말고 본인 터미널에서 환경변수로 직접 넣으세요.

## 실행

```bash
# 1회만 테스트 (현재 상태 즉시 확인)
python3 casper_subsidy_monitor.py --once

# Webhook 방식으로 상시 모니터링 (1시간 주기)
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/xxx/yyy" \
  python3 casper_subsidy_monitor.py

# Bot Token 방식
DISCORD_BOT_TOKEN="MT..." DISCORD_CHANNEL_ID="123456789" \
  python3 casper_subsidy_monitor.py

# 백그라운드 상시 실행 (로그 파일로)
DISCORD_WEBHOOK_URL="..." nohup python3 casper_subsidy_monitor.py > casper_monitor.log 2>&1 &
```

### 환경변수 옵션
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CASPER_REGION_CODE` | `4825` | 지자체 행정코드 (경남 김해시) |
| `CASPER_REGION_NAME` | `경남 김해시` | 알림 문구용 지역 이름 |
| `CASPER_INTERVAL_SEC` | `3600` | 폴링 주기(초) |
| `CASPER_NOTIFY_EACH_CHECK` | `0` | `1`이면 매 체크마다 현재상태도 전송(디버그) |

### 알림 동작 테스트
실제 마감→가능 전환을 기다리지 않고 알림이 가는지만 보려면:
```bash
DISCORD_WEBHOOK_URL="..." CASPER_NOTIFY_EACH_CHECK=1 \
  python3 casper_subsidy_monitor.py --once
```
매 체크 시 현재 상태 메시지를 한 번 보냅니다.

## 다른 지역 모니터링
`regionCode`만 바꾸면 됩니다. 행정코드 예: 서울특별시 1100 · 경남 48 · 김해시 4825.
정확한 시/군 코드는 견적 페이지에서 해당 지역 선택 시 호출되는
`region-info?regionCode=...` 요청에서 확인할 수 있습니다.
