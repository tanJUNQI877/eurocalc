#!/usr/bin/env python3
"""Update rates.json from the ECB Data Portal (public SDMX REST API).

- Inflation (HICP annual rate), ECB deposit rate and mortgage rate are updated automatically.
- VAT rates are NOT overwritten. They are legal facts that should be checked by a person.
  The script only compares them with a public list and reports differences.

Exit codes: 0 = all fine, 1 = ECB data could not be fetched at all,
            3 = ECB data updated, but VAT rates differ from the public list (please review).
Uses only the Python standard library.
"""
import datetime
import json
import pathlib
import sys
import urllib.request

ECB = "https://data-api.ecb.europa.eu/service/data"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RATES_FILE = ROOT / "rates.json"

# Euro-area member states (ISO codes as used by the ECB's ICP dataset)
EURO = ["AT", "BE", "BG", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE",
        "IT", "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES"]

VAT_CHECK_URL = "https://euvatrates.com/rates.json"


def http_json(url, timeout=30):
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


def fetch_series(flow, key):
    url = f"{ECB}/{flow}/{key}?lastNObservations=1&format=jsondata"
    return parse_sdmx(http_json(url))


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
    ok = 0
    failed = 0

    def update(setter, flow, key, label):
        nonlocal ok, failed
        try:
            value, period = fetch_series(flow, key)
            setter(value, period)
            ok += 1
            print(f"OK   {label}: {value} ({period})")
        except Exception as exc:  # keep the previous value on any failure
            failed += 1
            print(f"::warning::{label}: could not update ({exc}); keeping previous value")

    def set_top(name):
        def _set(v, p):
            data[name] = {"value": v, "period": p}
        return _set

    update(set_top("deposit"), "FM", "B.U2.EUR.4F.KR.DFR.LEV", "ECB deposit facility rate")
    update(set_top("inflation_ea"), "ICP", "M.U2.N.000000.4.ANR", "Euro-area HICP inflation")
    update(set_top("mortgage_ea"), "MIR", "M.U2.B.A2C.AM.R.A.2250.EUR.N",
           "Euro-area mortgage rate (new loans)")

    data.setdefault("inflation_country", {})
    for cc in EURO:
        def _set(v, p, cc=cc):
            data["inflation_country"][cc] = {"value": v, "period": p}
        update(_set, "ICP", f"M.{cc}.N.000000.4.ANR", f"HICP inflation {cc}")

    if ok == 0:
        print("::error::No ECB series could be fetched. rates.json was not changed.")
        return 1

    data["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    data["source"] = "ECB Data Portal (data-api.ecb.europa.eu), updated by scripts/update_rates.py"
    RATES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # VAT: report only, never overwrite
    code = 0
    try:
        diffs = vat_differences(data.get("vat", {}), http_json(VAT_CHECK_URL))
        for d in diffs:
            print(f"::warning::VAT check: {d}. Verify with the European Commission and edit rates.json by hand.")
        if diffs:
            code = 3
    except Exception as exc:
        print(f"::notice::VAT cross-check skipped ({exc})")
    return code


if __name__ == "__main__":
    sys.exit(main())
