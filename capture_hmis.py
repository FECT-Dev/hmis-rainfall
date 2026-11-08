import os

# ===== CONFIG (edit only this block) =====
URL = "https://hmis.gov.lk/customer/dashboard"
PERIODS = ["1H", "3H", "6H", "12H", "24H", "3D", "7D", "Daily"]
OUTPUT_DIR = "hmis_out"
IN_CI = os.getenv("CI") == "true"   # GitHub sets CI=true automatically
HEADLESS = IN_CI                    # no browser window on GitHub
NEEDS_LOGIN = not IN_CI             # manual login only when run on your PC
WAIT_SECONDS = 6                    # wait after each click for data to load

# Text each response's "message" must contain, so a late response from
# another period is never saved under the wrong name.
EXPECTED_MESSAGE = {
    "1H": "last 1 hours",
    "3H": "last 3 hours",
    "6H": "last 6 hours",
    "12H": "last 12 hours",
    "24H": "last 24 hours",
    "3D": "last 72 hours",
    "7D": "last 168 hours",
    "Daily": "daily",
}
# ===== END CONFIG =====

import pathlib, datetime
from zoneinfo import ZoneInfo
import pandas as pd
from playwright.sync_api import sync_playwright


def main():
    out = pathlib.Path(OUTPUT_DIR)
    out.mkdir(exist_ok=True)
    # Sri Lanka time, so file stamps match the site's reading times
    stamp = datetime.datetime.now(ZoneInfo("Asia/Colombo")).strftime("%Y%m%d_%H%M")
    saved = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()
        captured = []

        def on_response(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                if "json" not in resp.headers.get("content-type", ""):
                    return
                body = resp.json()
                # keep only rainfall responses
                if isinstance(body, dict) and "rainfall" in str(body.get("message", "")).lower():
                    captured.append((resp.url, body))
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(URL)
        if NEEDS_LOGIN:
            input("Log in, open the Real-Time Rainfall Map, then press Enter here...")
        else:
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(8000)

        for period in PERIODS:
            captured.clear()
            page.get_by_role("button", name=period, exact=True).click()
            page.wait_for_timeout(WAIT_SECONDS * 1000)

            want = EXPECTED_MESSAGE[period]
            matched = [(u, b) for u, b in captured
                       if want in str(b.get("message", "")).lower()]
            if not matched:
                print(f"{period}: no response containing '{want}'. Seen:",
                      [b.get("message") for _, b in captured])
            for i, (url, body) in enumerate(matched):
                data = body.get("data")
                if not isinstance(data, list) or not data:
                    print(f"{period}: response had no station data, skipped")
                    continue
                table = pd.DataFrame(data).drop(columns=["threshold_value"], errors="ignore")
                table.insert(0, "message", body.get("message"))
                f = out / f"{stamp}_{period}_{i}.csv"
                table.to_csv(f, index=False, encoding="utf-8")
                saved += 1
                print(period, "->", body.get("message"), f"({len(table)} rows)")

        browser.close()

    if saved == 0:
        raise SystemExit("Nothing captured. Failing the run so GitHub sends an alert.")


main()
