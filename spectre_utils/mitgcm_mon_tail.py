#!/usr/bin/env python3
"""
Tail an MITgcm STDOUT file and capture monitoring statistics (%MON) grouped by time_tsnumber.
Emits one JSON object per completed group (newline-delimited JSON) to STDOUT.
Optionally write to a file with --out.
Usage:
    python mitgcm_mon_tail.py /path/to/STDOUT.0000 [--from-start] [--out out.jsonl]
"""
import argparse, json, os, re, sys, time
from collections import OrderedDict
from spectre_utils import directorydb
from datetime import datetime

DBROOT=os.getenv("MON_DBROOT","monitoring")
ENSEMBLE_NAME=os.getenv("ENSEMBLE_NAME","test")
JOBID = os.getenv("JOBID",-1)
MEMBERID = os.getenv("MEMBERID","memb000")

MON_RE = re.compile(r".*%MON\s+([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
INT_RE = re.compile(r"[+-]?\d+$")
FLOAT_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?$")

# Local mongo db setup
DBCLIENT = directorydb.LocalMongo(DBROOT)
DB = DBCLIENT[ENSEMBLE_NAME]
COLLECTION = DB[MEMBERID]

def coerce_value(s: str):
    s = s.strip().rstrip(",")
    s2 = s.replace("D","e").replace("d","e")
    if INT_RE.fullmatch(s2):
        try:
            return int(s2)
        except Exception:
            pass
    if FLOAT_RE.fullmatch(s2):
        try:
            return float(s2)
        except Exception:
            pass
    return s

def emit_block(ts, block, outfh):
    if ts is None or not block:
        return

    # Add environment metadata
    block["job_id"] = JOBID
    # Add scrape timestamp
    block["_scraped_at"] = datetime.utcnow().isoformat() + "Z"

    # Ensure the ts is present inside the block
    if "time_tsnumber" not in block:
        block["time_tsnumber"] = ts
    rec = OrderedDict(sorted(block.items(), key=lambda kv: (kv[0]!="time_tsnumber", kv[0])))
    COLLECTION.insert_one(rec)
    line = json.dumps(rec)
    print(line, flush=True)

    if outfh is not None:
        outfh.write(line + "\n")
        outfh.flush()

def tail_file(path, from_start=False, out_path=None, poll_interval=0.25):
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(2)
    outfh = open(out_path, "a") if out_path else None
    try:
        with open(path, "r", errors="ignore") as f:
            if not from_start:
                f.seek(0, os.SEEK_END)
            current_ts = None
            current_block = OrderedDict()
            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    # Handle truncate/rotate: if file size < pos, seek to start
                    try:
                        size = os.path.getsize(path)
                        if size < pos:
                            f.seek(0, os.SEEK_SET)
                            current_ts = None
                            current_block = OrderedDict()
                    except FileNotFoundError:
                        pass
                    time.sleep(poll_interval)
                    continue
                m = MON_RE.match(line)
                if not m:
                    continue
                key, val = m.group(1), coerce_value(m.group(2))
                if key == "time_tsnumber":
                    new_ts = int(val)
                    if current_ts is not None and current_block:
                        emit_block(current_ts, current_block, outfh)
                        current_block = OrderedDict()
                    current_ts = new_ts
                    current_block[key] = val
                else:
                    if current_ts is None:
                        # ignore metrics until first time_tsnumber arrives
                        continue
                    if key in current_block:
                        existing = current_block[key]
                        if isinstance(existing, list):
                            existing.append(val)
                        else:
                            current_block[key] = [existing, val]
                    else:
                        current_block[key] = val
    finally:
        if outfh is not None:
            outfh.close()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="Path to MITgcm STDOUT file to tail")
    ap.add_argument("--from-start", action="store_true",
                    help="Parse the file from the beginning instead of tailing from the end")
    ap.add_argument("--out", help="Optional path to write newline-delimited JSON")
    ap.add_argument("--poll-interval", type=float, default=0.25, help="Polling interval in seconds")
    args = ap.parse_args()
    tail_file(args.path, from_start=args.from_start, out_path=args.out, poll_interval=args.poll_interval)

if __name__ == "__main__":
    main()
