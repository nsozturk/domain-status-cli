#!/usr/bin/env python3
# Written by Enes OZTURK.
import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Set

import websockets
try:
    from tqdm import tqdm  # type: ignore
except Exception:  # pragma: no cover - fallback if tqdm isn't installed
    def tqdm(iterable, desc="", unit="it"):
        total = len(iterable)
        start = time.time()
        last = start
        for i, item in enumerate(iterable, 1):
            now = time.time()
            if now - last >= 0.5 or i == total:
                elapsed = now - start
                rate = i / elapsed if elapsed > 0 else 0.0
                sys.stderr.write(
                    f"\r{desc}: {i}/{total} {unit} | {rate:.1f}/{unit}/s"
                )
                if i == total:
                    sys.stderr.write("\n")
                sys.stderr.flush()
                last = now
            yield item

WS_URL = "wss://domains-ws.revved.com/v1/ws?batch=false&whois=true&trace=true"
ORIGIN = "https://www.namecheap.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)


def load_bases(path: Path) -> List[str]:
    bases = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bases.append(line)
    return bases


def load_tlds(path: Path) -> List[str]:
    tlds = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tld = (row.get("tld") or "").strip().lower()
            if tld:
                tlds.append(tld)
    return tlds


def load_existing_domains(path: Path) -> Set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    existing: Set[str] = set()
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("domain") or "").strip().lower()
            if name:
                existing.add(name)
    return existing


def chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_domains(bases: List[str], tlds: List[str], use_tlds: bool) -> List[str]:
    if not use_tlds:
        return [b.strip().lower() for b in bases if b.strip()]
    domains = []
    for base in bases:
        base = base.strip().lower()
        if not base:
            continue
        for tld in tlds:
            domains.append(f"{base}.{tld.lower()}")
    return domains


async def query_domains(
    domains: List[str],
    batch_size: int,
    idle_timeout: float,
    progress_label: str,
) -> Dict[str, Dict]:
    results: Dict[str, Dict] = {}

    async with websockets.connect(
        WS_URL,
        additional_headers={"Origin": ORIGIN},
        user_agent_header=USER_AGENT,
        open_timeout=10,
        close_timeout=5,
    ) as ws:
        req_counter = 1
        batches = list(chunked(domains, batch_size))
        for batch in tqdm(batches, desc=progress_label, unit="batch"):
            req_id = f"{req_counter:06d}"
            req_counter += 1
            pending: Set[str] = set(batch)
            payload = {
                "type": "domainStatus",
                "reqID": req_id,
                "data": {"domains": batch},
            }
            await ws.send(json.dumps(payload))

            while pending:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=idle_timeout)
                except asyncio.TimeoutError:
                    break
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                if data.get("type") != "domainStatusResponse":
                    continue
                resp = data.get("data") or {}
                name = resp.get("name")
                if not name:
                    continue
                results[name] = resp
                pending.discard(name)

    return results


def append_csv(results: Dict[str, Dict], output: Path) -> None:
    needs_header = not output.exists() or output.stat().st_size == 0
    with output.open("a", newline="") as f:
        writer = csv.writer(f)
        if needs_header:
            writer.writerow(["domain", "available", "lookupType", "extra_json"])
        for domain in sorted(results.keys()):
            resp = results[domain]
            writer.writerow(
                [
                    domain,
                    resp.get("available"),
                    resp.get("lookupType"),
                    json.dumps(resp.get("extra"), separators=(",", ":")),
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query Namecheap WebSocket domainStatus and export latest responses."
    )
    parser.add_argument(
        "--bases",
        required=True,
        type=Path,
        help="Text file with base names (one per line).",
    )
    parser.add_argument(
        "--tlds",
        type=Path,
        default=Path("domain_extensions.csv"),
        help="CSV file with a 'tld' column.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("ws_domain_status.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="How many domains to send per WebSocket request.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=5.0,
        help="Seconds to wait without messages before moving on.",
    )
    parser.add_argument(
        "--no-tlds",
        action="store_true",
        help="Use --bases as full domains (do not append TLDs).",
    )
    args = parser.parse_args()

    bases = load_bases(args.bases)
    if not bases:
        raise SystemExit("No base domains found in --bases.")
    tlds = [] if args.no_tlds else load_tlds(args.tlds)
    if not args.no_tlds and not tlds:
        raise SystemExit("No TLDs found in --tlds.")

    existing = load_existing_domains(args.out)
    if existing:
        print(f"Resume: {len(existing)} domains already in {args.out}")

    for base in tqdm(bases, desc="Bases", unit="base"):
        domains_all = build_domains([base], tlds, use_tlds=not args.no_tlds)
        if not domains_all:
            print(f"Skip {base}: no domains to query")
            continue
        if existing.issuperset(domains_all):
            print(f"Skip {base}: all domains already exported")
            continue
        domains = [d for d in domains_all if d not in existing]
        base_results = asyncio.run(
            query_domains(
                domains,
                args.batch_size,
                args.idle_timeout,
                progress_label=f"Domains for {base}",
            )
        )
        append_csv(base_results, args.out)
        existing.update(base_results.keys())
        print(f"Wrote {len(base_results)} rows for {base} to {args.out}")


if __name__ == "__main__":
    main()
