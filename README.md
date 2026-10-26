# eori-number-check-python

Validate **EORI numbers** (Economic Operators Registration and Identification) against the official services, in Python, with **zero dependencies** (standard library only).

- **EU-27 and XI** (Northern Ireland) numbers → European Commission **EOS** SOAP service
- **GB** numbers → **HMRC** "Check EORI number" API (EOS no longer holds GB numbers since Brexit)
- Cleans input (`SE 556036-0793` → `SE5560360793`), checks the format locally, sends up to 10 numbers per EOS call, retries 5xx errors with backoff
- An outage or the EOS maintenance page is reported as `status: "unavailable"` with `valid: null`, **never as invalid**, so you don't reject a real trader because the upstream was down
- Sets its own User-Agent: EOS answers HTTP 502 to the default `python-requests` User-Agent

Neither service needs an API key or an account.

## Quick start

```bash
curl -O https://raw.githubusercontent.com/wsystemdev/eori-number-check-python/main/eori_check.py
python3 eori_check.py "SE 556036-0793" DE1234567 GB123456789000
```

Output (real run, 26 Oct 2026):

```json
{"eori": "SE5560360793", "valid": true, "status": "valid", "name": "SAAB Aktiebolag", "street": null, "postal_code": "58188", "city": "LINKÖPING", "country": "Sweden", "source": "EC EOS", "checked": "26/10/2026"}
{"eori": "DE1234567", "valid": false, "status": "invalid", "name": null, "street": null, "postal_code": null, "city": null, "country": null, "source": "EC EOS", "checked": "26/10/2026"}
{"eori": "GB123456789000", "valid": false, "status": "invalid", "name": null, "street": null, "postal_code": null, "city": null, "country": null, "source": "HMRC", "checked": "2026-10-26T09:54:02+00:00"}
```

Name and address only come back when the trader agreed to publish them, so a valid number without a name is normal.

## Batch from CSV

```bash
python3 eori_check.py --csv customers.csv --out results.csv
```

The CSV needs an `eori` column (or EORIs in the first column, no header). The exit code is `2` if any check was `unavailable`, so a cron job can retry later.

## In your code

```python
from eori_check import check_eoris

for r in check_eoris(["SE5560360793", "XI123456789000"]):
    if r["status"] == "unavailable":
        ...  # retry later, don't reject
    elif r["valid"]:
        print(r["eori"], r["name"])
```

`status` is one of `valid`, `invalid`, `format_error` (rejected locally, no call made) or `unavailable`.

## Tests

```bash
python3 -m unittest      # offline, mocks the HTTP calls
```

## Notes

- **EORI is not VAT.** A valid EU VAT number doesn't mean the company has an EORI, and vice versa. Check VAT numbers against VIES separately (see [vies-vat-validation-python](https://github.com/wsystemdev/vies-vat-validation-python)).
- EOS has maintenance windows. During them it redirects to an HTML page; this script detects that and marks the batch `unavailable`.
- Endpoints used: `https://ec.europa.eu/taxation_customs/dds2/eos/validation/services/validation` and `https://api.service.hmrc.gov.uk/customs/eori/lookup/check-multiple-eori`.

## Hosted alternative (disclosure: we're the maker)

This repo is free and standalone. If you'd rather not run it yourself, W System offers the same checks as a hosted service:

- REST: `GET https://api.wsystem.dev/eori?eori=SE5560360793` and `POST /eori/batch` (up to 100). 20 free calls/day per IP with no API key, then $0.01 per call via x402, or a monthly plan (Starter €19/month for 5,000 units). Docs: [EORI number check API](https://wsystem.dev/eori-number-check-api), prices: [wsystem.dev/pricing](https://wsystem.dev/pricing).
- MCP for AI agents: `https://api.wsystem.dev/mcp/` with `verify_eori` and `verify_eori_batch` tools ([eu-business-data-mcp](https://github.com/wsystemdev/eu-business-data-mcp)).
- Apify Actor for batch runs: [EU EORI Number Checker](https://apify.com/wsystem/eu-eori-checker).

## License

MIT
