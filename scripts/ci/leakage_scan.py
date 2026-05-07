"""Canary-based leakage detection between scorer and agent."""
import uuid
import sys
from pathlib import Path


def generate_canaries(n: int = 5) -> list[str]:
    return [f"CGA_CANARY__{uuid.uuid4().hex[:12]}" for _ in range(n)]


def scan_transcripts(transcript_dir: str | Path, canaries: list[str]) -> dict:
    hits = {c: 0 for c in canaries}
    transcript_path = Path(transcript_dir)
    if not transcript_path.exists():
        return {"total_hits": 0, "hits": hits, "passed": True}
    for f in transcript_path.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".txt", ".log", ".yaml"):
            try:
                text = f.read_text(errors="ignore")
                for c in canaries:
                    if c in text:
                        hits[c] += 1
            except Exception:
                pass
    total = sum(hits.values())
    return {"total_hits": total, "hits": hits, "passed": total == 0}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Transcript directory to scan")
    parser.add_argument("--canaries", type=int, default=5)
    args = parser.parse_args()

    canaries = generate_canaries(args.canaries)
    result = scan_transcripts(args.dir, canaries)
    print(f"Leakage scan: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Total hits: {result['total_hits']}")
    sys.exit(0 if result["passed"] else 1)
