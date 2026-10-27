"""Pre-run the demo examples so the app shows them instantly and offline.

    python -m b2g.demo.precompute

Uses the LLM from .env (answers are cached in results/cache/, so a re-run costs nothing).
The first example also runs S3 (pure LLM) for the "smart vs simple" tab.
"""

from __future__ import annotations

import sys

from b2g.agents.llm_client import get_client
from b2g.demo.core import EXAMPLES, run_example, save_example


def main() -> int:
    for i, (title, day, request) in enumerate(EXAMPLES):
        print(f"[{i + 1}/{len(EXAMPLES)}] {title} ({day}) ...", flush=True)
        data = run_example(day, request, title, with_s3=(i == 0))
        path = save_example(data)
        status = "ok" if data["ok"] else f"FAILED: {data['error']}"
        print(f"    {status}; constraints {data['constraints']}; saved {path.name}", flush=True)
    stats = get_client().stats.as_dict()
    print(f"LLM calls {stats['calls']} ({stats['cache_hits']} cached), tokens spent "
          f"{stats['prompt_tokens_spent'] + stats['completion_tokens_spent']}")
    return 0


if __name__ == "__main__":
    if not sys.flags.utf8_mode:   # same Windows encoding guard as b2g.cli
        import subprocess
        sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "b2g.demo.precompute"]))
    sys.exit(main())
