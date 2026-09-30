"""Console entry point. Reports go to stdout; operational errors go to stderr."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

from . import __version__
from .config import Config, PROBES, select_probes
from .mock import mock_server
from .plan import describe_plan
from .reporting import (compare, gate, read_report, render, render_comparison,
                        scrub, write_private)
from .runner import run_checks


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # Never echo arbitrary arguments: an accidentally pasted credential could be one.
        self.exit(2, "llm-handshake: invalid arguments. Run the command with --help for syntax.\n")


def parser() -> argparse.ArgumentParser:
    root = SafeParser(prog="llm-handshake", description="Inspect an LLM endpoint before integrating it.")
    root.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = root.add_subparsers(dest="command", required=True)

    def output(p: argparse.ArgumentParser) -> None:
        p.add_argument("--format", choices=("text", "json", "markdown"), default="text")
        p.add_argument("--output", metavar="FILE", help="Atomically write a private report instead of stdout.")

    for command in ("plan", "check"):
        p = commands.add_parser(command, help="Preview requests without network I/O." if command == "plan" else "Run explicitly selected probes.")
        p.add_argument("--base-url", help="API base including its prefix, e.g. /v1; defaults to OPENAI_BASE_URL.")
        p.add_argument("--model", help="Exact model identifier; defaults to OPENAI_MODEL.")
        p.add_argument("--api-key-env", default="OPENAI_API_KEY", metavar="NAME", help="Read the bearer token from this environment variable.")
        p.add_argument("--no-auth", action="store_true", help="Ignore the API-key variable; useful for local servers.")
        p.add_argument("--probes", default="models", help="Comma-separated names, or all: " + ", ".join(PROBES))
        p.add_argument("--timeout", type=float, default=20, help="Per-request timeout in seconds (default: 20).")
        p.add_argument("--max-output-tokens", type=int, default=128)
        p.add_argument("--token-limit-field", choices=("max_tokens", "max_completion_tokens"), default="max_tokens")
        p.add_argument("--max-requests", type=int, default=7)
        p.add_argument("--max-response-bytes", type=int, default=1_048_576)
        p.add_argument("--allow-http", action="store_true", help="Explicitly allow remote plaintext HTTP.")
        p.add_argument("--ca-file", help="Additional trust configuration through a PEM CA bundle.")
        if command == "check":
            p.add_argument("--allow-inference", action="store_true", help="Consent to the selected inference requests, which may be billed.")
            p.add_argument("--strict", action="store_true", help="Treat warnings and skipped checks as failures.")
            p.add_argument("--require", default="", help="Selected probes that must PASS, even without --strict.")
        output(p)
    p = commands.add_parser("demo", help="Exercise the real HTTP client against a temporary loopback mock.")
    p.add_argument("--broken", action="store_true", help="Demonstrate missing usage and malformed tool/JSON samples.")
    p.add_argument("--strict", action="store_true")
    output(p)
    p = commands.add_parser("compare", help="Detect probe-status regressions between JSON reports, offline.")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--allow-target-change", action="store_true")
    output(p)
    return root


def make_config(args: argparse.Namespace) -> Config:
    base = args.base_url if args.base_url is not None else os.environ.get("OPENAI_BASE_URL", "")
    if not base:
        raise ValueError("Set --base-url or OPENAI_BASE_URL. For a no-key demonstration, run llm-handshake demo.")
    key = "" if args.no_auth else os.environ.get(args.api_key_env, "")
    return Config(base_url=base, model=args.model if args.model is not None else os.environ.get("OPENAI_MODEL", ""),
                  api_key=key, probes=select_probes(args.probes), timeout=args.timeout,
                  allow_inference=getattr(args, "allow_inference", False), allow_http=args.allow_http,
                  max_output_tokens=args.max_output_tokens, token_limit_field=args.token_limit_field,
                  max_requests=args.max_requests, max_response_bytes=args.max_response_bytes, ca_file=args.ca_file)


def emit(text: str, destination: str | None) -> None:
    if destination:
        write_private(destination, text)
    else:
        sys.stdout.write(text)


def _plan_text(data: dict[str, Any], format: str) -> str:
    if format == "json":
        return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    heading = "# Request plan" if format == "markdown" else "Request plan (no requests sent)"
    lines = [heading, "", f"Requests: {data['request_count']}; inference requests: {data['inference_requests']}",
             f"Requested output-token ceiling: {data['requested_output_token_ceiling']}", data["billing_note"], ""]
    for request in data["requests"]:
        lines.append(f"{request['probe']:<14} {request['method']:<4} {request['relative_path']}")
    lines += ["", "Use --format json to inspect every synthetic request payload."]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "compare":
            comparison = compare(read_report(args.before), read_report(args.after), args.allow_target_change)
            emit(render_comparison(comparison, args.format), args.output)
            return 3 if comparison["regressions"] else 0
        if args.command == "demo":
            with mock_server(args.broken) as base:
                report = run_checks(Config(base, "handshake-demo", probes=PROBES, allow_inference=True))
            report["mode"] = "demo"
            emit(render(report, args.format), args.output)
            return gate(report, strict=args.strict)
        config = make_config(args)
        if args.command == "plan":
            data = describe_plan(config)
            # Only user-controlled fields can contain the configured credential.
            data["target"]["origin"] = scrub(data["target"]["origin"], config.api_key)
            data["target"]["model"] = scrub(data["target"]["model"], config.api_key)
            for request in data["requests"]:
                if request["payload"] is not None:
                    request["payload"]["model"] = scrub(request["payload"]["model"], config.api_key)
            emit(_plan_text(data, args.format), args.output)
            return 0
        required = select_probes(args.require) if args.require else ()
        if any(name not in config.probes for name in required):
            raise ValueError("Every --require probe must also be selected by --probes; no requests were sent.")
        report = run_checks(config)
        emit(render(report, args.format), args.output)
        return gate(report, strict=args.strict, required=required)
    except ValueError as error:
        sys.stderr.write("llm-handshake: " + str(error) + "\n")
        return 2
    except OSError:
        sys.stderr.write("llm-handshake: could not access a local file; check the path and permissions.\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("llm-handshake: interrupted. No automatic retries were made.\n")
        return 130


def entrypoint() -> None:
    raise SystemExit(main())
