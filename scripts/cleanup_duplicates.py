# scripts/cleanup_duplicates.py
# One-off cleanup: removes duplicate documents (same sha256), keeping the most
# pipeline-advanced copy of each. Deletes both the data/raw folder and the
# document's vectors in Qdrant. Run with --dry-run to preview without deleting.
import argparse
import json
import shutil
import sys
from pathlib import Path

from qdrant_client import QdrantClient, models

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402

STATUS_RANK = {"embedded": 4, "chunked": 3, "parsed": 2, "uploaded": 1, "failed": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    raw = Path(settings.data_dir) / "raw"
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=30)

    by_sha: dict[str, list[dict]] = {}
    orphans: list[Path] = []
    for d in raw.iterdir():
        if not d.is_dir():
            continue
        m = d / "manifest.json"
        if not m.exists():
            orphans.append(d)  # folder without manifest: unreachable via the API
            continue
        rec = json.loads(m.read_text(encoding="utf-8"))
        by_sha.setdefault(rec["sha256"], []).append(rec)

    def delete_doc(doc_id: str, name: str, status: str, reason: str) -> None:
        print(f"DELETE {doc_id}  {name}  status={status}  ({reason})")
        if args.dry_run:
            return
        client.delete(
            settings.collection_name,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="document_id", match=models.MatchValue(value=doc_id))])),
        )
        shutil.rmtree(raw / doc_id, ignore_errors=True)

    for sha, recs in sorted(by_sha.items()):
        recs.sort(key=lambda r: (STATUS_RANK.get(r["status"], 0), r["upload_date"]), reverse=True)
        keeper, dupes = recs[0], recs[1:]
        print(f"KEEP   {keeper['document_id']}  {keeper['document_name']}  status={keeper['status']}")
        for r in dupes:
            delete_doc(r["document_id"], r["document_name"], r["status"], f"duplicate of {keeper['document_id']}")

    for d in orphans:
        print(f"DELETE {d.name}  (orphan folder, no manifest)")
        if not args.dry_run:
            client.delete(
                settings.collection_name,
                points_selector=models.FilterSelector(filter=models.Filter(must=[
                    models.FieldCondition(key="document_id", match=models.MatchValue(value=d.name))])),
            )
            shutil.rmtree(d, ignore_errors=True)

    total = client.count(settings.collection_name, exact=True).count
    print(f"\nVectors remaining in '{settings.collection_name}': {total}")


if __name__ == "__main__":
    main()
