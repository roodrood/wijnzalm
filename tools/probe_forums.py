#!/usr/bin/env python3
"""Read-only connection diagnosis: homepage and robots.txt only, not a crawler."""
import argparse
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser

SITES = {
    "lapassionduvin": "https://www.lapassionduvin.com",
    "vinejo": "https://www.vinejo.freebb.be",
}
USER_AGENT = "WijnzalmProbe/0.1 (+https://github.com/roodrood/wijnzalm; diagnostic only)"

class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlparse(req.full_url).hostname
        if urlparse(newurl).hostname not in {old, old.removeprefix("www."), "www." + old.removeprefix("www.")}:
            raise URLError("Redirect to another host refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

OPENER = build_opener(SameHostRedirect())

def fetch_status(url):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain,text/html;q=0.9"})
    try:
        with OPENER.open(request, timeout=12) as response:
            return {"http_status": response.status, "final_url": response.url,
                    "sample_bytes": len(response.read(65536))}
    except HTTPError as exc:
        return {"http_status": exc.code, "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"http_status": None, "error": f"{type(exc).__name__}: {exc}"[:350]}

def robots_status(url):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"})
    try:
        with OPENER.open(request, timeout=12) as response:
            data = response.read(256000)
            text = data.decode("utf-8", errors="replace")
            parser = RobotFileParser()
            parser.parse(text.splitlines())
            return {"http_status": response.status, "bytes": len(data),
                    "root_can_fetch": parser.can_fetch(USER_AGENT, url.removesuffix("robots.txt")),
                    "robots_readable": response.status == 200}
    except HTTPError as exc:
        return {"http_status": exc.code, "robots_readable": False,
                "note": "Cannot determine crawl permission from this check"}
    except Exception as exc:
        return {"http_status": None, "robots_readable": False,
                "error": f"{type(exc).__name__}: {exc}"[:350]}

def probe_site(site, origin):
    domain = urlparse(origin).hostname
    result = {"site": site, "origin": origin,
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "probe_is_not_crawl_authorization": True}
    try:
        answers = sorted({item[4][0] for item in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)})
        result["dns"] = {"ok": True, "addresses": answers[:6]}
    except Exception as exc:
        result["dns"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:350]}
    result["homepage"] = fetch_status(origin + "/")
    time.sleep(1.5)
    result["robots"] = robots_status(origin + "/robots.txt")
    result["verdict"] = ("network_reachable" if result["homepage"].get("http_status") == 200
                         else "needs_investigation")
    return result

def markdown_report(rows):
    lines = ["# Wineforum connection probe", "",
             "Diagnostic only; no discussion pages or posts downloaded.", "",
             "| Forum | DNS | Homepage HTTP | robots.txt HTTP | Outcome |",
             "|---|---|---:|---:|---|"]
    for row in rows:
        h = row["homepage"].get("http_status")
        r = row["robots"].get("http_status")
        lines.append(f'| {row["site"]} | {"OK" if row["dns"]["ok"] else "FAIL"} | '
                     f'{h if h is not None else "error"} | {r if r is not None else "error"} | {row["verdict"]} |')
    lines.extend(["", "Next: review site policies and obtain required authorization before archiving forum content.", ""])
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="probe-results")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    rows = [probe_site(name, url) for name, url in SITES.items()]
    (out / "probe.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "REPORT.md").write_text(markdown_report(rows), encoding="utf-8")
    print(markdown_report(rows))
    print(f"Results: {out.resolve()}")

if __name__ == "__main__":
    main()
