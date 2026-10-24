#!/usr/bin/env python3
"""Bounded, robots-aware topic metadata indexer. Never archives message bodies."""
import argparse
import hashlib
import json
import re
import sqlite3
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from urllib.robotparser import RobotFileParser
from urllib.request import Request
from urllib.error import HTTPError
from probe_forums import OPENER, USER_AGENT

SITES = {
    "lpv": {"seed":"https://www.lapassionduvin.com/forum/bourgognebeaujolais/47053-domaine-de-suremain",
            "origin":"https://www.lapassionduvin.com","host":"www.lapassionduvin.com"},
    "vinejo": {"seed":"http://www.vinejo.freebb.be/thread-4841.html",
               "origin":"http://www.vinejo.freebb.be","host":"www.vinejo.freebb.be"},
}

def canonical(site,url):
    conf=SITES[site]
    p=urlparse(url)
    if p.scheme!=urlparse(conf["origin"]).scheme or p.hostname!=conf["host"]:
        return None
    if site=="lpv":
        if not re.search(r"/47053-domaine-de-suremain/?$",p.path):return None
        start=parse_qs(p.query).get("start",["0"])[0]
        query=urlencode({"start":start}) if start.isdigit() and 0<int(start)<20000 else ""
    else:
        if not re.match(r"^/thread-4841(?:-page-\d+|-post-\d+)?\.html$",p.path):
            return None
        query=""
    return urlunparse((p.scheme,p.netloc,p.path,"",query,""))

class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self.seen=set()
        self.post_markers=0
        self.title_capture=False
        self.title=""
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=="a" and d.get("href") and d["href"] not in self.seen:
            self.links.append(d["href"])
            self.seen.add(d["href"])
        if tag=="title":self.title_capture=True
        classes=set((d.get("class") or "").split())
        if "kmsg" in classes or "post_content" in classes:
            self.post_markers+=1
    def handle_endtag(self,tag):
        if tag=="title":self.title_capture=False
    def handle_data(self,data):
        if self.title_capture:self.title+=data[:160]

def get_robots(site):
    req=Request(SITES[site]["origin"]+"/robots.txt",headers={"User-Agent":USER_AGENT})
    with OPENER.open(req,timeout=15) as r:
        if r.status!=200:raise RuntimeError("robots.txt not HTTP 200; stopping")
        lines=r.read(256000).decode("utf-8",errors="replace").splitlines()
    p=RobotFileParser()
    p.parse(lines)
    return p

def run(site,out_dir,max_pages):
    conf=SITES[site]
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(out/"frontier.sqlite")
    conn.execute("CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY,status TEXT,sha256 TEXT,html_title TEXT,post_markers INTEGER,discovered_at TEXT)")
    conn.execute("INSERT OR IGNORE INTO pages(url,status) VALUES (?,?)",(conf["seed"],"pending"))
    conn.commit()
    robots=get_robots(site)
    count=0
    failures=[]
    while count<max_pages:
        row=conn.execute("SELECT url FROM pages WHERE status='pending' ORDER BY url LIMIT 1").fetchone()
        if not row:break
        url=row[0]
        if not robots.can_fetch(USER_AGENT,url):
            conn.execute("UPDATE pages SET status=? WHERE url=?",("robots-denied",url))
            conn.commit()
            continue
        if count:time.sleep(4.0)
        try:
            req=Request(url,headers={"User-Agent":USER_AGENT,"Accept":"text/html"})
            with OPENER.open(req,timeout=18) as resp:
                if resp.status!=200:raise RuntimeError(f"HTTP {resp.status}")
                if urlparse(resp.url).hostname!=conf["host"]:raise RuntimeError("cross-host redirect")
                body=resp.read(750001)
            if len(body)>750000:raise RuntimeError("oversized page")
            meta=Metadata()
            meta.feed(body.decode("utf-8",errors="replace"))
            for href in meta.links:
                link=canonical(site,urljoin(url,href))
                if link and robots.can_fetch(USER_AGENT,link):
                    conn.execute("INSERT OR IGNORE INTO pages(url,status) VALUES (?,?)",(link,"pending"))
            conn.execute('UPDATE pages SET status=?,sha256=?,html_title=?,post_markers=?,discovered_at=datetime("now") WHERE url=?',
                         ("ok",hashlib.sha256(body).hexdigest(),meta.title.strip()[:150],meta.post_markers,url))
            conn.commit()
            count+=1
        except HTTPError as exc:
            failures.append(f"{url}: HTTP {exc.code}")
            conn.execute("UPDATE pages SET status=? WHERE url=?",(f"HTTP-{exc.code}",url))
            conn.commit()
            if exc.code==429 or exc.code>=500:break
        except Exception as exc:
            failures.append(f"{url}: {type(exc).__name__}: {exc}")
            conn.execute("UPDATE pages SET status=? WHERE url=?",("error",url))
            conn.commit()
            break
    pages=[{"url":u,"status":s,"sha256":h,"html_title":t,"post_markers":n} for u,s,h,t,n in
           conn.execute("SELECT url,status,sha256,html_title,post_markers FROM pages ORDER BY url")]
    report={"site":site,"pages_fetched":count,"pages_discovered":len(pages),
            "failures":failures,"scope":"one topic only; HTML bodies not stored","pages":pages}
    (out/"index.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    (out/"INDEX.md").write_text("# "+site+" topic metadata index\n\n"+
        f"Fetched {count} pages, discovered {len(pages)} URLs; **not a full forum crawl**.\n\n"+
        "".join(f'- [{p["status"]}] {p["url"]} — message blocks: {p["post_markers"]}\n' for p in pages),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--site",choices=SITES,required=True)
    p.add_argument("--out",default="probe-results/topic-index")
    p.add_argument("--max-pages",type=int,default=2)
    args=p.parse_args()
    if not 1<=args.max_pages<=10:p.error("max-pages must be 1..10")
    result=run(args.site,args.out,args.max_pages)
    print(json.dumps({k:v for k,v in result.items() if k!="pages"},ensure_ascii=False))

if __name__=="__main__":main()
