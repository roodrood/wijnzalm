#!/usr/bin/env python3
"""Test one public topic per forum only if robots.txt allows it. No post text is stored."""
import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request
from urllib.robotparser import RobotFileParser
from probe_forums import OPENER, USER_AGENT

TARGETS = {
    "lapassionduvin": "https://www.lapassionduvin.com/forum/bourgognebeaujolais/47053-domaine-de-suremain",
    "vinejo": "http://www.vinejo.freebb.be/thread-4841.html",
}

class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = Counter()
        self.classes = Counter()
        self.ids = Counter()
    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        d = dict(attrs)
        for name in (d.get("class") or "").split():
            if any(s in name.lower() for s in ("post","msg","message","pagination","page","kunena")):
                self.classes[name] += 1
        val = (d.get("id") or "").lower()
        if any(x in val for x in ("post","msg","message")):
            self.ids[val[:70]] += 1

def fetch_structure(name,url):
    origin = urlparse(url).scheme + "://" + urlparse(url).netloc
    result = {"forum":name,"url":url,"metadata_only":True,"insecure_transport":urlparse(url).scheme!="https"}
    try:
        req = Request(origin+"/robots.txt",headers={"User-Agent":USER_AGENT})
        with OPENER.open(req,timeout=12) as response:
            if response.status != 200:
                return {**result,"result":"skipped_robots_not_200","robots_http_status":response.status}
            rules = response.read(256000).decode("utf-8",errors="replace")
        parser = RobotFileParser()
        parser.parse(rules.splitlines())
        allowed = parser.can_fetch(USER_AGENT,url)
        result["robots_allows_thread"] = allowed
        if not allowed:
            return {**result,"result":"skipped_robots_disallow"}
        req = Request(url,headers={"User-Agent":USER_AGENT,"Accept":"text/html"})
        with OPENER.open(req,timeout=12) as response:
            b = response.read(256001)
            result["http_status"] = response.status
            result["final_url"] = response.url
        if result["http_status"]!=200:
            return {**result,"result":"non_200"}
        h = Structure()
        h.feed(b[:256000].decode("utf-8",errors="replace"))
        return {**result,"result":"parsed_one_page","bytes_read":len(b),
                "truncated":len(b)>256000,"html_tags":h.tags.most_common(12),
                "postlike_classes":h.classes.most_common(20),"postlike_id_count":len(h.ids),
                "postlike_id_prefixes":Counter(k.split("_")[0] for k in h.ids).most_common(12)}
    except Exception as exc:
        return {**result,"result":"error","error":f"{type(exc).__name__}: {exc}"[:350]}

def main():
    results = [fetch_structure(name,url) for name,url in TARGETS.items()]
    folder = Path("probe-results")
    folder.mkdir(exist_ok=True)
    (folder/"structure.json").write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
    lines = ["# Forum HTML structure sample","","One topic per forum, subject to robots rules; content not archived.",""]
    for r in results:
        lines.append(f"## {r['forum']}")
        lines.append(f"- Status: {r['result']}")
        lines.append(f"- URL: {r['url']}")
        lines.append(f"- Insecure HTTP: {r['insecure_transport']}")
        lines.append(f"- Post-like classes: {r.get('postlike_classes','not available')}")
        lines.append("")
    (folder/"structure.md").write_text("\n".join(lines),encoding="utf-8")
    print("\n".join(lines))
if __name__=="__main__": main()
