#!/usr/bin/env python3
"""Bounded public forum metadata discovery. No post bodies saved.
One manual run per workflow; respect robots, max page budget, host, and crawl delay.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from urllib.robotparser import RobotFileParser
from urllib.request import Request
from urllib.error import HTTPError, URLError
from probe_forums import OPENER, USER_AGENT

FORUMS = {
    "lpv": {
        "root": "https://www.lapassionduvin.com",
        "seeds": ["/forum/bourgognebeaujolais/", "/forum/bordeaux/"],
        "host": "www.lapassionduvin.com",
    },
    "vinejo": {
        "root": "http://www.vinejo.freebb.be",
        "seeds": ["/", "/thread-4841.html"],
        "host": "www.vinejo.freebb.be",
    },
}
MAX_BYTES = 500_000
DELAY_SECONDS = 5.0

class LinksAndMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.title_parts = []
        self.in_title = False
        self.post_markers = 0
        self.titles = 0
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
        if tag == "title":
            self.in_title = True
        classes = set((d.get("class") or "").split())
        if "kmsg" in classes or "post_content" in classes:
            self.post_markers += 1
    def handle_endtag(self,tag):
        if tag == "title":
            self.in_title = False
    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data[:200])
    @property
    def title(self):
        return " ".join(" ".join(self.title_parts).split())[:160]

def clean_url(site, url, allow_indexes=True):
    cfg = FORUMS[site]
    p = urlparse(url)
    origin = urlparse(cfg["root"])
    if p.hostname != cfg["host"] or p.scheme != origin.scheme or p.port not in (None, 80 if p.scheme == "http" else 443):
        return None
    path = p.path or "/"
    query = ""
    if site == "lpv":
        path = re.sub(r"/+", "/", path)
        if path.startswith("/forum/"):
            tail = path[len("/forum/"):]
        else:
            tail = path.lstrip("/")
        if tail.startswith("bourgognebeaujolais"):
            if re.fullmatch(r"bourgognebeaujolais/\d+-[^/]+/?", tail):
                pass
            elif allow_indexes and re.fullmatch(r"bourgognebeaujolais/?", tail):
                pass
            else:
                return None
        elif tail.startswith("bordeaux"):
            if re.fullmatch(r"bordeaux/\d+-[^/]+/?", tail):
                pass
            elif allow_indexes and re.fullmatch(r"bordeaux/?", tail):
                pass
            else:
                return None
        else:
            return None
        path = "/forum/" + tail.rstrip("/")
        start = parse_qs(p.query).get("start", ["0"])[0]
        if start.isdigit() and 0 < int(start) <= 10000:
            query = urlencode({"start":start})
    else:
        if allow_indexes and path == "/":
            pass
        elif allow_indexes and re.fullmatch(r"/forum-\d+(?:-page-\d+)?\.html", path):
            pass
        elif re.fullmatch(r"/thread-\d+(?:-page-\d+)?\.html", path):
            pass
        else:
            return None
    return urlunparse((origin.scheme, cfg["host"], path, "", query, ""))

def topic_identity(site, url):
    if not is_topic(site,url):
        return None
    path = urlparse(url).path
    if site == "lpv":
        m = re.search(r"/(\\d+)-[^/]+$",path)
        return m.group(1) if m else None
    m = re.search(r"/thread-(\\d+)",path)
    return m.group(1) if m else None

def is_topic(site, url):
    p = urlparse(url)
    if site == "lpv":
        return bool(re.search(r"/\d+-[^/]+$", p.path))
    return bool(re.fullmatch(r"/thread-\d+(?:-page-\d+)?\.html", p.path))

def robots(site):
    cfg = FORUMS[site]
    req = Request(cfg["root"] + "/robots.txt", headers={"User-Agent":USER_AGENT})
    with OPENER.open(req, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError("robots not 200; stop")
        body = response.read(256_000)
    rules = RobotFileParser()
    rules.parse(body.decode("utf-8", errors="replace").splitlines())
    return rules

def crawl(site, out_path, max_pages, max_topics):
    cfg = FORUMS[site]
    out = Path(out_path)
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out / "frontier.sqlite")
    db.execute("""CREATE TABLE IF NOT EXISTS pages(
        url TEXT PRIMARY KEY, status TEXT NOT NULL, title TEXT, page_sha256 TEXT,
        post_markers INTEGER DEFAULT 0, level TEXT, last_checked_utc TEXT
    )""")
    db.execute("CREATE TABLE IF NOT EXISTS log_events(datetime_utc TEXT, url TEXT, event TEXT)")
    for seed in cfg["seeds"]:
        canonical = clean_url(site, urljoin(cfg["root"],seed))
        if canonical:
            db.execute("INSERT OR IGNORE INTO pages(url,status,level) VALUES (?,?,?)",
                       (canonical,"pending","index" if not is_topic(site, canonical) else "topic"))
    db.commit()
    rule = robots(site)
    report = {"site":site, "started_utc":datetime.now(timezone.utc).isoformat(),
              "scope":"bounded metadata only; no forum post text retained",
              "max_pages":max_pages, "max_topics":max_topics, "errors":[]}
    fetched = 0
    fetched_topics = 0
    while fetched < max_pages:
        indexes_indexed = db.execute("SELECT count(*) FROM pages WHERE level='index' AND status='ok'").fetchone()[0]
        priority_index = indexes_indexed < (2 if site == "lpv" else 3)
        row = db.execute("""SELECT url,level FROM pages
                            WHERE status='pending' ORDER BY
                            CASE WHEN level=? THEN 0 ELSE 1 END,
                            CASE WHEN instr(url,'?')>0 THEN 1 ELSE 0 END,
                            url LIMIT 1""",("index" if priority_index else "topic",)).fetchone()
        if not row:
            break
        url, level = row
        if level == "topic" and fetched_topics >= max_topics:
            break
        if not rule.can_fetch(USER_AGENT, url):
            db.execute("UPDATE pages SET status='robots-denied' WHERE url=?",(url,))
            db.commit()
            continue
        if fetched:
            time.sleep(DELAY_SECONDS)
        try:
            req = Request(url,headers={"User-Agent":USER_AGENT,"Accept":"text/html"})
            with OPENER.open(req,timeout=20) as r:
                if r.status != 200:
                    raise RuntimeError("non-200 response")
                if urlparse(r.url).hostname != cfg["host"]:
                    raise RuntimeError("cross-host redirect refused")
                page = r.read(MAX_BYTES+1)
            if len(page) > MAX_BYTES:
                raise RuntimeError("page too large; no metadata indexed")
            parser = LinksAndMetadata()
            parser.feed(page.decode("utf-8",errors="replace"))
            added_indexes = 0
            for link in parser.links:
                nxt = clean_url(site,urljoin(url,link))
                if not nxt:
                    continue
                level_nxt = "topic" if is_topic(site,nxt) else "index"
                # Keep index traversal bounded so the budget reaches actual discussions.
                if level_nxt == "index":
                    if urlparse(nxt).query or added_indexes >= (4 if site == "vinejo" else 0):
                        continue
                    if site == "vinejo" and nxt.endswith("/"):
                        continue
                    added_indexes += 1
                db.execute("INSERT OR IGNORE INTO pages(url,status,level) VALUES (?,?,?)",
                           (nxt,"pending",level_nxt))
            now = datetime.now(timezone.utc).isoformat()
            db.execute("""UPDATE pages SET status=?,title=?,page_sha256=?,
                          post_markers=?,last_checked_utc=? WHERE url=?""",
                       ("ok",parser.title,hashlib.sha256(page).hexdigest(),parser.post_markers,now,url))
            db.commit()
            fetched += 1
            fetched_topics += int(level == "topic")
        except HTTPError as exc:
            db.execute("UPDATE pages SET status=? WHERE url=?",(f"HTTP-{exc.code}",url))
            db.commit()
            report["errors"].append({"url":url,"error":f"HTTP {exc.code}"})
            if exc.code == 429 or exc.code >= 500:
                break
        except Exception as exc:
            db.execute("UPDATE pages SET status='error' WHERE url=?",(url,))
            db.commit()
            report["errors"].append({"url":url,"error":f"{type(exc).__name__}: {exc}"[:240]})
            break
    data = [dict(url=u,status=s,title=t,sha256=h,post_markers=n,level=l,checked_at=dt)
            for u,s,t,h,n,l,dt in db.execute("SELECT url,status,title,page_sha256,post_markers,level,last_checked_utc FROM pages ORDER BY level,url")]
    unique_topic_ids = set(topic_identity(site,x["url"]) for x in data if x["status"]=="ok" and is_topic(site,x["url"]))
    discovered_topic_ids = set(topic_identity(site,x["url"]) for x in data if is_topic(site,x["url"]))
    report.update({"ended_utc":datetime.now(timezone.utc).isoformat(),
                   "pages_fetched_this_run":fetched,
                   "topics_fetched_this_run":fetched_topics,
                   "unique_urls_discovered":len(data),
                   "topics_discovered":sum(is_topic(site,x["url"]) for x in data),
                   "unique_topics_discovered":len(discovered_topic_ids),
                   "unique_topics_sampled":len(unique_topic_ids),
                   "total_pages_indexed":sum(x["status"]=="ok" for x in data),
                   "total_topic_pages_indexed":sum(x["status"]=="ok" and x["level"]=="topic" for x in data),
                   "post_block_occurrences":sum(x["post_markers"] or 0 for x in data if x["status"]=="ok"),
                   "pages":data})
    (out/"metadata.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    text = [f"# {site}: topic metadata pilot","",
            f"- Pages indexed: {report['total_pages_indexed']}",
            f"- Topic pages indexed: {report['total_topic_pages_indexed']}",
            f"- Topic URLs discovered: {report['topics_discovered']}",
            f"- Unique topics discovered: {report['unique_topics_discovered']}",
            f"- Unique topics sampled: {report['unique_topics_sampled']}",
            f"- Post-block occurrences: {report['post_block_occurrences']} (not deduplicated posts)",
            f"- Fetch errors: {len(report['errors'])}","",
            "This is a bounded pilot, not a complete forum archive.","",
            "## Indexed pages"]
    for entry in data:
        if entry["status"] == "ok":
            text.append(f'- [{entry["level"]}] {entry["title"] or "untitled"} — {entry["url"]} ({entry["post_markers"]} post blocks)')
    (out/"INDEX.md").write_text("\n".join(text)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="pages"},ensure_ascii=False))
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--site",choices=FORUMS,required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--max-pages",type=int,default=12)
    p.add_argument("--max-topics",type=int,default=8)
    a=p.parse_args()
    if not 1<=a.max_pages<=25 or not 1<=a.max_topics<=20:
        p.error("limits: pages <=25; topics <=20")
    crawl(a.site,a.out,a.max_pages,a.max_topics)

if __name__=="__main__":
    main()
