#!/usr/bin/env python3
"""
캐스퍼 일렉트릭 전기차 구매보조금 신청가능 모니터링

현대 캐스퍼 견적 페이지가 내부적으로 호출하는 공개 API를 1시간(기본) 주기로 폴링한다.
지정한 지자체(기본: 경남 김해시, regionCode=4825)의 보조금 신청 상태가
"임시중단/마감"(finalSubsidyApplyState == 'F', "다음 공모를 기다려주세요") 에서
"신청 가능" 으로 바뀌면 Discord 로 알림을 보낸다.

API:  GET https://casper.hyundai.com/gw/wp/product/v2/product/elec-subsidy/region-info
      ?regionCode=<code>&receiptScnCode=E&targetUserCode=01
  - 인증/쿠키 불필요 (순수 GET).
  - 응답 data.finalSubsidyApplyState : 'F' = 마감/중단, 그 외 = 접수중(가능)으로 간주
  - 응답 data.pcExposureSbc          : 화면 노출 문구

환경변수(택1):
  DISCORD_WEBHOOK_URL                 : 디스코드 웹훅 URL  (가장 간단, 권장)
  또는
  DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID : 봇 토큰 + 채널 ID

선택 환경변수:
  CASPER_REGION_CODE  (기본 4825 = 경남 김해시)
  CASPER_REGION_NAME  (기본 "경남 김해시" — 알림 문구용)
  CASPER_INTERVAL_SEC (기본 3600 = 1시간)
  CASPER_NOTIFY_EACH_CHECK (1 이면 매 체크마다 현재상태도 보고 — 디버그용)
  CASPER_STATE_FILE   (상태 저장 파일 경로. 기본: 스크립트 옆 casper_monitor_state.json)

사용:
  DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." python3 casper_subsidy_monitor.py
  # 또는
  DISCORD_BOT_TOKEN="..." DISCORD_CHANNEL_ID="123..." python3 casper_subsidy_monitor.py
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

API_URL = (
    "https://casper.hyundai.com/gw/wp/product/v2/product/elec-subsidy/region-info"
    "?regionCode={code}&receiptScnCode=E&targetUserCode=01"
)
ESTIMATION_PAGE = "https://casper.hyundai.com/vehicles/electric/making/model"

REGION_CODE = os.environ.get("CASPER_REGION_CODE", "4825")
REGION_NAME = os.environ.get("CASPER_REGION_NAME", "경남 김해시")
INTERVAL_SEC = int(os.environ.get("CASPER_INTERVAL_SEC", "3600"))
NOTIFY_EACH_CHECK = os.environ.get("CASPER_NOTIFY_EACH_CHECK", "0") == "1"

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "").strip()

STATE_FILE = os.environ.get(
    "CASPER_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "casper_monitor_state.json"),
)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def fetch_status():
    """region-info API 호출. (available: bool, data: dict) 반환. 실패 시 예외."""
    url = API_URL.format(code=REGION_CODE)
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    data = (payload or {}).get("data") or {}
    state = data.get("finalSubsidyApplyState")
    msg = data.get("pcExposureSbc") or ""
    # 'F' = 마감/중단. 그 외(비어있지 않은 값)이면 접수 가능으로 간주.
    # 추가 안전장치: 문구에 '기다려' 가 사라지고 '신청'/'가능' 이 나타나도 가능으로 판단.
    available = False
    if state and state != "F":
        available = True
    if msg and ("기다려" not in msg) and (("신청" in msg) or ("가능" in msg)):
        available = True
    return available, data


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_discord(content: str) -> bool:
    """Discord 로 메시지 전송. webhook 우선, 없으면 bot token 사용."""
    data = json.dumps({"content": content}).encode("utf-8")
    try:
        if WEBHOOK_URL:
            req = urllib.request.Request(
                WEBHOOK_URL, data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status in (200, 204)
        elif BOT_TOKEN and CHANNEL_ID:
            req = urllib.request.Request(
                f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bot {BOT_TOKEN}",
                    "User-Agent": "CasperSubsidyMonitor (https://casper.hyundai.com, 1.0)",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status in (200, 201)
        else:
            log("⚠️  Discord 자격증명 미설정 — 콘솔에만 출력합니다.")
            log("    DISCORD_WEBHOOK_URL 또는 (DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID) 를 설정하세요.")
            return False
    except urllib.error.HTTPError as e:
        log(f"❌ Discord 전송 실패 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
        return False
    except Exception as e:  # noqa: BLE001
        log(f"❌ Discord 전송 오류: {e}")
        return False


def build_available_message(data: dict) -> str:
    notice = data.get("publicNoticeCount", "?")
    receipt = data.get("receiptCount", "?")
    remain = "?"
    try:
        remain = int(notice) - int(receipt)
    except (TypeError, ValueError):
        pass
    return (
        f"🚨 **캐스퍼 EV 보조금 신청 가능!** 🚨\n"
        f"📍 지역: **{REGION_NAME}** (regionCode={REGION_CODE})\n"
        f"✅ 상태: 보조금을 신청할 수 있어요!\n"
        f"📊 공고 {notice}대 / 접수 {receipt}대 / 잔여 약 {remain}대\n"
        f"💬 문구: {data.get('pcExposureSbc', '')}\n"
        f"🔗 견적/계약: {ESTIMATION_PAGE}\n"
        f"⏰ 감지시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"@everyone 서둘러 신청하세요!"
    )


def run_once_and_notify(state: dict) -> dict:
    """한 번 체크하고 상태 변화 시 알림. 갱신된 state 반환."""
    try:
        available, data = fetch_status()
    except Exception as e:  # noqa: BLE001
        log(f"⚠️  API 호출 실패: {e}")
        return state

    cur_flag = data.get("finalSubsidyApplyState")
    cur_msg = data.get("pcExposureSbc", "")
    log(f"[{REGION_NAME}] state={cur_flag} available={available} msg='{cur_msg}'")

    prev_available = state.get("available")

    if available and not prev_available:
        # 마감 -> 가능 으로 전환된 순간!
        log("🎉 신청 가능으로 전환 감지! Discord 알림 전송")
        ok = send_discord(build_available_message(data))
        log("   → 전송 성공" if ok else "   → 전송 실패(콘솔 확인)")
    elif NOTIFY_EACH_CHECK:
        ok = send_discord(
            f"[모니터링 테스트] {REGION_NAME} 현재 {'가능✅' if available else '마감/대기⏳'} "
            f"(state={cur_flag}, msg='{cur_msg}')"
        )
        log("   → 디스코드 전송 성공" if ok else "   → 디스코드 전송 실패")

    state.update({
        "available": available,
        "finalSubsidyApplyState": cur_flag,
        "pcExposureSbc": cur_msg,
        "lastCheck": datetime.now().isoformat(timespec="seconds"),
        "regionCode": REGION_CODE,
        "regionName": REGION_NAME,
    })
    save_state(state)
    return state


def main():
    once = "--once" in sys.argv
    log("=== 캐스퍼 EV 보조금 모니터 시작 ===")
    log(f"지역: {REGION_NAME} (regionCode={REGION_CODE}) / 주기: {INTERVAL_SEC}s")
    if WEBHOOK_URL:
        log("알림 방식: Discord Webhook")
    elif BOT_TOKEN and CHANNEL_ID:
        log("알림 방식: Discord Bot Token")
    else:
        log("⚠️  Discord 미설정 — 콘솔 출력만 (테스트 모드)")

    state = load_state()
    state = run_once_and_notify(state)

    if once:
        log("--once 모드: 1회 체크 후 종료")
        return

    while True:
        try:
            time.sleep(INTERVAL_SEC)
        except KeyboardInterrupt:
            log("종료합니다.")
            break
        state = run_once_and_notify(state)


if __name__ == "__main__":
    main()
