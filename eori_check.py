#!/usr/bin/env python3
"""Validate EORI numbers against the official services. Zero dependencies (stdlib only).

- EU-27 and XI (Northern Ireland) numbers: European Commission EOS SOAP service
- GB numbers: HMRC "Check EORI number" API

An upstream outage is reported as status "unavailable" (valid=None), never as invalid.
"""
import argparse, csv, json, re, sys, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET

__version__ = "0.1.0"
EOS_URL = "https://ec.europa.eu/taxation_customs/dds2/eos/validation/services/validation"
HMRC_URL = "https://api.service.hmrc.gov.uk/customs/eori/lookup/check-multiple-eori"
UA = f"eori-number-check-python/{__version__} (+https://github.com/wsystemdev/eori-number-check-python)"
EORI_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{1,15}$")
EU_PREFIXES = set("AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK XI".split())


def clean(eori):
    """Strip spaces, dots and dashes; uppercase."""
    return re.sub(r"[\s.\-]", "", str(eori)).upper()


def _post(url, data, headers, timeout, retries):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **headers})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return e.code, e.read(), url
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        if attempt < retries:
            time.sleep(1.5 * (2 ** attempt))
    raise ConnectionError(str(last))


def _check_eos(eoris, timeout, retries):
    body = "".join(f"<ev:eori>{e}</ev:eori>" for e in eoris)
    env = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
           f'<ev:validateEORI xmlns:ev="http://eori.ws.eos.dds.s/">{body}</ev:validateEORI>'
           '</soap:Body></soap:Envelope>')
    status, raw, final_url = _post(EOS_URL, env.encode(), {"Content-Type": "text/xml; charset=utf-8"}, timeout, retries)
    # During maintenance EOS redirects to an HTML "sorry" page instead of answering
    if status != 200 or "sorry" in final_url or b"validateEORIResponse" not in raw:
        raise ConnectionError(f"EOS unavailable (HTTP {status}, {final_url})")
    root = ET.fromstring(raw)
    req_date = next((d.text for d in root.iter("requestDate")), None)
    out = {}
    for res in root.iter("result"):
        item = {c.tag: (c.text or "").strip() for c in res}
        e = item.get("eori", "")
        out[e] = {"eori": e, "valid": item.get("status") == "0", "status": "valid" if item.get("status") == "0" else "invalid",
                  "name": item.get("name") or None, "street": item.get("street") if item.get("street") not in (None, "", ".") else None,
                  "postal_code": item.get("postalCode") or None, "city": item.get("city") or None,
                  "country": item.get("country") or None, "source": "EC EOS", "checked": req_date}
    return out


def _check_hmrc(eoris, timeout, retries):
    status, raw, _ = _post(HMRC_URL, json.dumps({"eoris": eoris}).encode(),
                           {"Content-Type": "application/json", "Accept": "application/vnd.hmrc.1.0+json"}, timeout, retries)
    if status != 200:
        raise ConnectionError(f"HMRC unavailable (HTTP {status})")
    out = {}
    for item in json.loads(raw):
        e = item.get("eori", "")
        addr = item.get("companyDetails", {}).get("address", {}) if item.get("companyDetails") else {}
        out[e] = {"eori": e, "valid": bool(item.get("valid")), "status": "valid" if item.get("valid") else "invalid",
                  "name": (item.get("companyDetails") or {}).get("traderName"), "street": addr.get("streetAndNumber"),
                  "postal_code": addr.get("postcode"), "city": addr.get("cityName"), "country": "United Kingdom" if item.get("valid") else None,
                  "source": "HMRC", "checked": item.get("processingDate")}
    return out


def check_eoris(eoris, timeout=15, retries=2):
    """Validate a list of EORI numbers. Returns one dict per input, in input order."""
    cleaned = [clean(e) for e in eoris]
    results = {}
    eu, gb = [], []
    for e in dict.fromkeys(cleaned):
        if not EORI_RE.match(e) or e[:2] not in EU_PREFIXES | {"GB"}:
            results[e] = {"eori": e, "valid": False, "status": "format_error", "source": "local"}
        elif e.startswith("GB"):
            gb.append(e)
        else:
            eu.append(e)
    for chunk_size, items, fn in ((10, eu, _check_eos), (10, gb, _check_hmrc)):
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i + chunk_size]
            try:
                results.update(fn(chunk, timeout, retries))
            except (ConnectionError, ET.ParseError, ValueError) as err:
                for e in chunk:
                    results[e] = {"eori": e, "valid": None, "status": "unavailable", "error": str(err)}
            for e in chunk:
                results.setdefault(e, {"eori": e, "valid": None, "status": "unavailable", "error": "no result returned"})
    return [results[e] for e in cleaned]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate EORI numbers (EU/XI via EC EOS, GB via HMRC).")
    ap.add_argument("eori", nargs="*", help="EORI numbers")
    ap.add_argument("--csv", help="CSV file with an 'eori' column (or EORIs in the first column)")
    ap.add_argument("--out", help="write results as CSV to this file instead of JSON lines to stdout")
    a = ap.parse_args(argv)
    eoris = list(a.eori)
    if a.csv:
        with open(a.csv, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        header = [c.strip().lower() for c in rows[0]] if rows else []
        if "eori" in header:
            col, start = header.index("eori"), 1
        else:
            col, start = 0, 0
        eoris += [r[col] for r in rows[start:] if r and r[col].strip()]
    if not eoris:
        ap.error("give EORI numbers or --csv")
    res = check_eoris(eoris)
    if a.out:
        keys = ["eori", "status", "valid", "name", "street", "postal_code", "city", "country", "source", "checked", "error"]
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(res)
    else:
        for r in res:
            print(json.dumps(r, ensure_ascii=False))
    return 0 if all(r["status"] != "unavailable" for r in res) else 2


if __name__ == "__main__":
    sys.exit(main())
