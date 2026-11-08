# ===== CONFIG (edit only this block) =====
INPUT_DIR = "hmis_out"
OUTPUT_CSV = "hmis_rainfall_long.csv"
DISTRICTS = []             # e.g. ["Kandy", "Kegalle"]; empty list = all districts
WINDOW_HOURS = {"Daily": 24, "1H": 1, "3H": 3, "6H": 6, "12H": 12,
                "24H": 24, "3D": 72, "7D": 168}
GRACE_HOURS = 1            # allowance for reporting delay
VALID_STATUSES = ["Rained", "Raining", "No Rain"]
EXCLUDE_IDS = ["test device id"]
SKIP_STAMPS = []           # runs to ignore (start of the file names), e.g. ["20261103_1127"]
# ===== END CONFIG =====

import pathlib, re
import pandas as pd

frames = []
for f in sorted(pathlib.Path(INPUT_DIR).glob("*.csv")):
    if any(f.name.startswith(s) for s in SKIP_STAMPS):
        continue
    m = re.match(r"(\d{8}_\d{4})_(\w+?)_\d+\.csv", f.name)
    if not m:
        continue
    raw = pd.read_csv(f, dtype=str, keep_default_na=False)
    raw = raw[raw["sensor_type"] == "Rainfall"]
    frames.append(pd.DataFrame({
        "captured_at": pd.to_datetime(m.group(1), format="%Y%m%d_%H%M"),
        "period": m.group(2),
        "message": raw["message"],
        "institute": raw["institute"].str.strip(),
        "device_id": raw["device_id"].str.strip(),
        "device_name": raw["device_name"].str.strip(),
        "district": raw["district_name"].str.strip(),
        "lat": raw["latitude"],
        "lon": raw["longitude"],
        "reading_time": raw["timestamp"],
        "status": raw["status"],
        "value_mm": raw["value"],
    }))

if not frames:
    raise SystemExit("No CSV files found in hmis_out. Run capture_hmis.py first.")

df = pd.concat(frames, ignore_index=True)
df = df[~df["device_id"].isin(EXCLUDE_IDS)]
df["lat"] = pd.to_numeric(df["lat"].astype(str).str.strip(), errors="coerce")
df["lon"] = pd.to_numeric(df["lon"].astype(str).str.strip(), errors="coerce")
df["value_mm"] = pd.to_numeric(df["value_mm"], errors="coerce").round(2)
df["reading_time"] = pd.to_datetime(df["reading_time"], format="%m/%d/%Y, %I:%M:%S %p", errors="coerce")

# flag readings that are missing or older than the period's window
age_h = (df["captured_at"] - df["reading_time"]).dt.total_seconds() / 3600
window_h = df["period"].map(WINDOW_HOURS)
df["is_stale"] = df["reading_time"].isna() | (age_h > window_h + GRACE_HOURS)
df["valid"] = df["status"].isin(VALID_STATUSES) & ~df["is_stale"]

if DISTRICTS:
    df = df[df["district"].isin(DISTRICTS)]

# newest capture wins when the same reading appears in more than one run
df = df.sort_values("captured_at").drop_duplicates(
    subset=["device_id", "period", "reading_time"], keep="last")
df.to_csv(OUTPUT_CSV, index=False)

print(df.groupby("period")["valid"].agg(["size", "sum"])
        .rename(columns={"size": "stations", "sum": "valid"}))
print(f"Saved {len(df)} rows to {OUTPUT_CSV}")
