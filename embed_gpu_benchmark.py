"""
Embedding throughput benchmark — how long to embed ~1 GB of text?
=================================================================

Runs in Google Colab (CUDA GPU), in VSCode on an Apple-Silicon Mac (MPS GPU),
or anywhere on CPU. It measures the *real* embedding rate (chunks/second) on a
representative sample, then extrapolates to a full 1 GB document.

WHY A SAMPLE + EXTRAPOLATE (and not literally embed 1 GB):
  Embedding rate is steady, so you don't need to embed all of 1 GB to know the
  time — measure the rate on, say, 20k chunks and multiply. You CAN embed the
  whole thing by setting RUN_FULL = True (slow, and downloads/holds more data).

NOTE ON "movie/video": a text-embedding model can only embed TEXT, not video
bytes. So SOURCE_URL points at a large public-domain TEXT file; the script
replicates it to reach the target size for timing purposes.

------------------------------------------------------------------
COLAB QUICK START:
  1. Runtime -> Change runtime type -> Hardware accelerator -> GPU
  2. Paste this whole file into a cell and run it.
------------------------------------------------------------------
"""

# ── In Colab this installs the deps; locally it's a no-op if already present ──
try:
    import sentence_transformers  # noqa: F401
    import torch  # noqa: F401
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                           "sentence-transformers"])

import time
import urllib.request

import torch
from sentence_transformers import SentenceTransformer


# ─────────────────────────── CONFIG (tweak me) ───────────────────────────
MODEL_NAME   = "BAAI/bge-small-en-v1.5"   # same model our app uses (384-dim)
TARGET_GB    = 1.0                        # the document size we want a time for
CHUNK_CHARS  = 2000                       # ~500 tokens per chunk (our app targets 512)
BATCH_SIZE   = 256                        # encode batch size (raise on a big GPU)
SAMPLE_CHUNKS = 20_000                    # how many chunks to actually time
RUN_FULL     = False                      # True = embed the whole TARGET_GB (slow)

# A large public-domain text file (Complete Works of Shakespeare, ~5 MB).
# Replace with any .txt URL you like — it's only used as raw material.
SOURCE_URL   = "https://www.gutenberg.org/files/100/100-0.txt"
# ──────────────────────────────────────────────────────────────────────────


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"          # Apple-Silicon GPU
    return "cpu"


def fetch_text(url: str) -> str:
    print(f"Downloading source text from {url} ...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", errors="replace")
        print(f"  got {len(text)/1e6:.1f} MB of text")
        return text
    except Exception as e:
        print(f"  download failed ({e}); falling back to synthetic text")
        return ("The quick brown fox studies object oriented programming, "
                "inheritance and polymorphism in great detail. ") * 5000


def build_chunks(text: str, n_chunks: int, chunk_chars: int) -> list[str]:
    """Slice text into chunk_chars-sized pieces, cycling through the text to
    reach n_chunks (repetition is fine — we're timing throughput, not quality)."""
    pieces = [text[i:i + chunk_chars] for i in range(0, len(text), chunk_chars)
              if text[i:i + chunk_chars].strip()]
    if not pieces:
        pieces = ["empty"]
    chunks = []
    while len(chunks) < n_chunks:
        chunks.extend(pieces)
    return chunks[:n_chunks]


def main():
    device = pick_device()
    gpu_name = torch.cuda.get_device_name(0) if device == "cuda" else device
    print(f"\nDevice: {device}  ({gpu_name})")
    print(f"Model:  {MODEL_NAME}\n")

    model = SentenceTransformer(MODEL_NAME, device=device)

    # How many chunks does TARGET_GB of text correspond to?
    total_chunks_target = int(TARGET_GB * 1e9 / CHUNK_CHARS)
    n_sample = total_chunks_target if RUN_FULL else min(SAMPLE_CHUNKS, total_chunks_target)

    text = fetch_text(SOURCE_URL)
    chunks = build_chunks(text, n_sample, CHUNK_CHARS)
    print(f"\nTarget: {TARGET_GB} GB  ->  ~{total_chunks_target:,} chunks "
          f"of {CHUNK_CHARS} chars")
    print(f"Timing on {len(chunks):,} chunks (batch_size={BATCH_SIZE})...\n")

    # Warm up (first batch pays model-to-GPU transfer + kernel compile)
    model.encode(chunks[:BATCH_SIZE], batch_size=BATCH_SIZE,
                 show_progress_bar=False, normalize_embeddings=True)

    t0 = time.perf_counter()
    model.encode(chunks, batch_size=BATCH_SIZE, show_progress_bar=True,
                 normalize_embeddings=True, convert_to_numpy=True)
    dt = time.perf_counter() - t0

    rate = len(chunks) / dt
    est_full = total_chunks_target / rate
    vec_gb = total_chunks_target * 384 * 4 / 1e9   # float32 vectors for full doc

    print("\n────────────────────── RESULTS ──────────────────────")
    print(f"Device                 : {device} ({gpu_name})")
    print(f"Chunks embedded (timed): {len(chunks):,} in {dt:.1f}s")
    print(f"Throughput             : {rate:,.0f} chunks/sec")
    print(f"--- Extrapolated to {TARGET_GB} GB of text ---")
    print(f"Total chunks           : ~{total_chunks_target:,}")
    print(f"Estimated embed time   : {est_full/60:,.1f} min  ({est_full:,.0f}s)")
    print(f"Output vector size     : ~{vec_gb:.2f} GB (float32, 384-dim)")
    print("──────────────────────────────────────────────────────")
    if not RUN_FULL:
        print("(estimate from sample; set RUN_FULL=True to embed the whole 1 GB)")


if __name__ == "__main__":
    main()
