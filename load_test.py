"""
Concurrent upload load test — simulates N users uploading documents simultaneously.

Each upload streams SSE events until the document is embedded or failed.
Reports per-document timing and overall throughput.

Usage:
    python load_test.py --token <JWT> --docs 20 --concurrency 4 --dir /tmp/wiki-large
    python load_test.py --token <JWT> --docs 5  --concurrency 2 --dir /tmp/wiki-docs

The token is your Supabase JWT (copy from Swagger after authenticating).
"""
import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000/v1"


@dataclass
class DocResult:
    filename: str
    doc_id: str = ""
    upload_start: float = 0.0
    embedded_at: float = 0.0
    status: str = "pending"
    error: str = ""
    events: list[str] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return self.embedded_at - self.upload_start if self.embedded_at else 0.0


async def upload_and_stream(
    client: httpx.AsyncClient,
    path: Path,
    token: str,
    sem: asyncio.Semaphore,
    results: list[DocResult],
    idx: int,
) -> None:
    result = DocResult(filename=path.name)
    results[idx] = result

    async with sem:
        result.upload_start = time.perf_counter()
        print(f"  ↑ [{idx+1}] Uploading {path.name[:50]} ...")

        try:
            async with client.stream(
                "POST",
                f"{BASE_URL}/documents",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (path.name, path.read_bytes(), "text/plain")},
                timeout=600,
            ) as resp:
                if resp.status_code not in (200, 201):
                    body = await resp.aread()
                    result.status = "http_error"
                    result.error = f"HTTP {resp.status_code}: {body[:200].decode()}"
                    print(f"  ✗ [{idx+1}] {result.error}")
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    status = event.get("status", "")
                    result.events.append(status)

                    if not result.doc_id and "document_id" in event:
                        result.doc_id = event["document_id"]

                    if status == "embedded":
                        result.status = "embedded"
                        result.embedded_at = time.perf_counter()
                        elapsed = result.total_seconds
                        print(f"  ✓ [{idx+1}] {path.name[:40]} → embedded in {elapsed:.1f}s")
                        return

                    if status == "failed":
                        result.status = "failed"
                        result.embedded_at = time.perf_counter()
                        result.error = event.get("error", "unknown")
                        print(f"  ✗ [{idx+1}] {path.name[:40]} FAILED: {result.error[:80]}")
                        return

        except Exception as exc:
            result.status = "exception"
            result.error = str(exc)
            result.embedded_at = time.perf_counter()
            print(f"  ✗ [{idx+1}] Exception: {exc}")


def print_report(results: list[DocResult], wall_time: float):
    ok     = [r for r in results if r.status == "embedded"]
    failed = [r for r in results if r.status != "embedded"]

    print(f"\n{'='*62}")
    print(f"  Load Test Results")
    print(f"{'='*62}")
    print(f"  Total docs   : {len(results)}")
    print(f"  Embedded     : {len(ok)}")
    print(f"  Failed       : {len(failed)}")
    print(f"  Wall time    : {wall_time:.1f}s")

    if ok:
        times = [r.total_seconds for r in ok]
        print(f"\n  Per-document processing time:")
        print(f"    Min   : {min(times):.1f}s")
        print(f"    Max   : {max(times):.1f}s")
        print(f"    Avg   : {sum(times)/len(times):.1f}s")
        print(f"\n  Throughput:")
        docs_per_min = len(ok) / wall_time * 60
        print(f"    {docs_per_min:.1f} docs/min  ({len(ok)/wall_time:.2f} docs/sec)")
        print(f"    Extrapolated: {docs_per_min*60:.0f} docs/hr  |  {docs_per_min*1440:.0f} docs/day")

    if failed:
        print(f"\n  Failed documents:")
        for r in failed:
            print(f"    {r.filename[:40]}: {r.status} — {r.error[:60]}")

    if ok:
        print(f"\n  Per-doc breakdown:")
        print(f"  {'#':<4} {'File':<42} {'Time':>7} {'Status'}")
        print(f"  {'─'*58}")
        for i, r in enumerate(results, 1):
            t = f"{r.total_seconds:.1f}s" if r.total_seconds else "—"
            print(f"  {i:<4} {r.filename[:42]:<42} {t:>7}  {r.status}")

    print(f"{'='*62}\n")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token",       required=True, help="Supabase JWT token")
    parser.add_argument("--docs",        type=int, default=10,
                        help="Number of documents to upload")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Max simultaneous uploads (= Celery workers)")
    parser.add_argument("--dir",         default="/tmp/wiki-large",
                        help="Directory of .txt files to upload")
    parser.add_argument("--url",         default="http://localhost:8000",
                        help="Base server URL")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = f"{args.url.rstrip('/')}/v1"

    doc_dir = Path(args.dir)
    files = sorted(doc_dir.glob("*.txt"))[: args.docs]
    if not files:
        files = sorted(doc_dir.glob("*.pdf"))[: args.docs]
    if not files:
        print(f"No .txt or .pdf files found in {doc_dir}"); return

    total_mb = sum(f.stat().st_size for f in files) / 1024**2
    print(f"\n{'='*62}")
    print(f"  Concurrent Upload Load Test")
    print(f"  Server      : {BASE_URL}")
    print(f"  Documents   : {len(files)}  ({total_mb:.1f} MB total)")
    print(f"  Concurrency : {args.concurrency} simultaneous uploads")
    print(f"{'='*62}\n")

    sem = asyncio.Semaphore(args.concurrency)
    results: list[DocResult] = [None] * len(files)  # type: ignore

    async with httpx.AsyncClient(timeout=None) as client:
        t0 = time.perf_counter()
        await asyncio.gather(*[
            upload_and_stream(client, path, args.token, sem, results, i)
            for i, path in enumerate(files)
        ])
        wall_time = time.perf_counter() - t0

    print_report(results, wall_time)


if __name__ == "__main__":
    asyncio.run(main())
