# scripts/migrate_local_to_qdrant.py
"""One-off migration: pushes the documents under data/raw/ (raw file, manifest.json,
parsed.json, chunks.json) into the Qdrant Cloud document store used by QdrantStorage.

Run from the project root so .env is picked up:
    python scripts/migrate_local_to_qdrant.py

After verifying the API works against the cloud, the local data/ directory can be deleted.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients import build_qdrant_client
from app.config import get_settings
from app.storage import QdrantStorage, RAW_BLOB, MANIFEST_BLOB, PARSED_BLOB, CHUNKS_BLOB

DATA_ROOT = Path("data") / "raw"
ARTIFACT_FILES = {"parsed.json": PARSED_BLOB, "chunks.json": CHUNKS_BLOB}


async def main() -> None:
    settings = get_settings()
    client = build_qdrant_client(settings)
    storage = QdrantStorage(client, settings)
    await storage.ensure_collection()
    try:
        if not DATA_ROOT.exists():
            print(f"Nothing to migrate: {DATA_ROOT} does not exist")
            return
        for doc_dir in sorted(p for p in DATA_ROOT.iterdir() if p.is_dir()):
            manifest_path = doc_dir / "manifest.json"
            if not manifest_path.exists():
                print(f"SKIP {doc_dir.name}: no manifest.json")
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            doc_id = manifest["document_id"]

            raw_path = doc_dir / manifest["document_name"]
            if raw_path.exists():
                await storage.put_blob(doc_id, RAW_BLOB, raw_path.read_bytes())
            else:
                print(f"WARN {doc_id}: raw file '{manifest['document_name']}' not found")

            for filename, blob_name in ARTIFACT_FILES.items():
                artifact = doc_dir / filename
                if artifact.exists():
                    await storage.put_blob(doc_id, blob_name, artifact.read_bytes())

            # Manifest goes last and with the storage_path rewritten to its cloud location,
            # so a document only becomes listable once all its blobs are uploaded
            manifest["storage_path"] = f"qdrant://{settings.docs_collection_name}/{doc_id}/{RAW_BLOB}"
            await storage.put_blob(doc_id, MANIFEST_BLOB,
                                   json.dumps(manifest, indent=2).encode("utf-8"))
            print(f"OK   {doc_id}  {manifest['document_name']}  (status={manifest.get('status')})")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
