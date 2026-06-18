"""
Admin reset: wipes all documents and vectors directly via Qdrant client.
No HTTP auth needed — run locally with the venv active.

    python scripts/reset_data.py
    python scripts/reset_data.py --confirm   # skip the y/n prompt
"""
import asyncio
import argparse
import sys

from app.config import get_settings
from app.clients import build_qdrant_client
from app.storage import QdrantStorage
from app.store.qdrant_store import VectorStore
from app.ingestion.service import IngestionService


async def reset(confirm: bool):
    settings = get_settings()
    qdrant = build_qdrant_client(settings)

    try:
        storage = QdrantStorage(qdrant, settings)
        vector_store = VectorStore(qdrant, settings)
        ingestion = IngestionService(settings, storage)

        # Show what will be deleted
        records = await ingestion.list_all()
        print(f"\nFound {len(records)} document(s):")
        for r in records:
            print(f"  {r.document_name:<40} status={r.status.value}  user={r.user_id or 'None'}")

        if not records and not await qdrant.collection_exists(vector_store.collection):
            print("\nNothing to clear. Already empty.")
            return

        if not confirm:
            ans = input(f"\nDelete all {len(records)} doc(s) and recreate collections? [y/N] ")
            if ans.strip().lower() != "y":
                print("Aborted.")
                return

        print("\nClearing document blobs...")
        for r in records:
            await storage.cleanup(r.document_id)
            print(f"  deleted {r.document_name}")

        print("Recreating vector collection...")
        if await qdrant.collection_exists(vector_store.collection):
            await qdrant.delete_collection(vector_store.collection)
        await vector_store.ensure_collection()

        print("Recreating document storage collection...")
        if await qdrant.collection_exists(storage.collection):
            await qdrant.delete_collection(storage.collection)
        await storage.ensure_collection()

        print(f"\nDone. Cleared {len(records)} document(s). Both collections recreated fresh.")

    finally:
        await qdrant.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true",
                        help="Skip confirmation prompt")
    args = parser.parse_args()
    asyncio.run(reset(args.confirm))
