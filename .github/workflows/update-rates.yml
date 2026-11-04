#!/usr/bin/env python3
"""Update rates.json from the ECB Data Portal (public SDMX REST API).

- Inflation (HICP annual rate), ECB deposit rate and mortgage rate are updated automatically.
- VAT rates are NOT overwritten. They are legal facts that should be checked by a person.
  The script only compares them with a public list and reports differences.

Exit codes: 0 = ECB data updated (VAT differences are only printed as notices),
            1 = ECB data could not be fetched at all (the job turns red and GitHub emails you).
Uses only the Python standard library.
"""
import datetime
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ECB = "https://data-api.ecb.europa.eu/service/data"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RATES_FILE = ROOT / "rates.json"

# Euro-area member states (ISO codes as used by the ECB's ICP dataset)
EURO = ["AT", "BE", "BG", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE",
        "IT", "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES"]

VAT_CHECK_URL = "https://euvatrates.com/rates.json"


def http_json(url, timeout=25):
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "eurocalc-rates-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_sdmx(js):
    """Return (value, period) of the latest observation in an SDMX-JSON response."""
    series = js["dataSets"][0]["series"]
    skey = next(iter(series))
    obs = series[skey]["observations"]
    idx = max(obs, key=int)
    value = obs[idx][0]
    if value is None:
        raise ValueError("empty observation")
    periods = js["structure"]["dimensions"]["observation"][0]["values"]
    return round(float(value), 2), periods[int(idx)]["id"]


def fetch_series(flow, key, attempts=4):
    """Fetch one series, retrying with a growing pause (the ECB API is sometimes slow)."""
    url = f"{ECB}/{flow}/{key}?lastNObservations=1&format=jsondata"
    last_exc = None
    for i in range(attempts):
        try:
            return parse_sdmx(http_json(url))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (400, 404):  # wrong key or no data: retrying will not help
                break
        except Exception as exc:
            last_exc = exc
        if i < attempts - 1:
            time.sleep(3 * (i + 1))
    raise last_exc


def vat_differences(current, public):
    """Compare our standard VAT rates with a public list. Returns a list of messages."""
    diffs = []
    rates = (public or {}).get("rates", {})
    for code, info in rates.items():
        cc = "GR" if code == "EL" else code
        theirs = info.get("standard_rate") if isinstance(info, dict) else None
        ours = current.get(cc)
        if isinstance(theirs, (int, float)) and ours is not None and abs(theirs - ours) > 1e-9:
            diffs.append(f"{cc}: rates.json has {ours}, public list says {theirs}")
    return diffs


def main():
    data = json.loads(RATES_FILE.read_text(encoding="utf-8"))

    # (label, flow, key, where to store)
    jobs = [
        ("ECB deposit facility rate", "FM", "B.U2.EUR.4F.KR.DFR.LEV", ("deposit", None)),
        ("Euro-area HICP inflation", "ICP", "M.U2.N.000000.4.ANR", ("inflation_ea", None)),
        ("Euro-area mortgage rate (new loans)", "MIR", "M.U2.B.A2C.AM.R.A.2250.EUR.N", ("mortgage_ea", None)),
    ] + [
        (f"HICP inflation {cc}", "ICP", f"M.{cc}.N.000000.4.ANR", ("inflation_country", cc))
        for cc in EURO
    ]

    def run(job):
        label, flow, key, dest = job
        try:
            return job, fetch_series(flow, key), None
        except Exception as exc:
            return job, None, exc

    ok = 0
    data.setdefault("inflation_country", {})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, jobs))
    for job, res, exc in results:
        label, _flow, _key, (name, cc) = job
        if exc is not None:
            print(f"::warning::{label}: could not update ({exc}); keeping previous value")
            continue
        value, period = res
        entry = {"value": value, "period": period}
        if cc:
            data["inflation_country"][cc] = entry
        else:
            data[name] = entry
        ok += 1
        print(f"OK   {label}: {value} ({period})")
    print(f"{ok} of {len(jobs)} series updated")

    if ok == 0:
        print("::error::No ECB series could be fetched. rates.json was not changed.")
        return 1

    data["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    data["source"] = "ECB Data Portal (data-api.ecb.europa.eu), updated by scripts/update_rates.py"
    RATES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # VAT: never overwritten. The public list used for comparison can itself be out of date,
    # so differences are shown as a notice only. Check VAT rates by hand every few months.
    try:
        diffs = vat_differences(data.get("vat", {}), http_json(VAT_CHECK_URL))
        for d in diffs:
            print(f"::notice::VAT cross-check: {d}. The public list may be outdated; verify with the European Commission.")
    except Exception as exc:
        print(f"::notice::VAT cross-check skipped ({exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
