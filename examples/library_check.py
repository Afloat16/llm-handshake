"""Explicitly opted-in real-endpoint example; not part of the demo or test suite."""
from __future__ import annotations

import os
import sys

from llm_handshake import Config, run_checks
from llm_handshake.reporting import gate, render


def main() -> int:
    # Environment-based consent prevents a copied example from silently billing.
    if os.environ.get("HANDSHAKE_ALLOW_INFERENCE") != "1":
        print("Set HANDSHAKE_ALLOW_INFERENCE=1 to authorize two potentially billable requests.", file=sys.stderr)
        return 2
    try:
        config = Config(
            base_url=os.environ["OPENAI_BASE_URL"],
            model=os.environ["OPENAI_MODEL"],
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            probes=("chat", "stream"),
            allow_inference=True,
            max_requests=2,
        )
        report = run_checks(config)
    except (KeyError, ValueError):
        print("Configure a valid OPENAI_BASE_URL and OPENAI_MODEL; review local settings.", file=sys.stderr)
        return 2
    print(render(report), end="")
    return gate(report, required=("chat", "stream"))


if __name__ == "__main__":
    raise SystemExit(main())
