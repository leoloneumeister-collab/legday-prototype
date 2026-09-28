"""Jarvis CLI.

    python -m jarvis doctor                 # what is configured, what is reachable
    python -m jarvis brief                  # the real thing: fetch, think, email
    python -m jarvis brief --offline        # fixtures, no network at all
    python -m jarvis brief --dry-run        # print what the model would be sent
    python -m jarvis brief --no-send        # print the brief instead of emailing it
    python -m jarvis brief --record         # also dump raw API payloads for debugging
    python -m jarvis snapshot               # just save today's positions
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .brief import build_bundle, render_markdown
from .claude_client import ClaudeError, generate_brief
from .config import FIXTURES_DIR, LIVE_FIXTURES_DIR, STATE_DIR, Config
from .delivery import email as email_delivery
from .prompt import build_system_prompt
from .snapshots import build_snapshot, diff_snapshots, load_previous, save_snapshot, today_iso
from .sources import congress as congress_source
from .sources import finlight, trading212
from .sources.base import SourceResult

OK = "✓"
BAD = "✗"


# --------------------------------------------------------------------------- io

def _load_fixture(name: str) -> Any:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _make_recorder(enabled: bool):
    if not enabled:
        return None

    def record(name: str, payload: Any) -> None:
        LIVE_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        target = LIVE_FIXTURES_DIR / f"{today_iso()}_{name}.json"
        target.write_text(json.dumps(payload, indent=2)[:5_000_000], encoding="utf-8")
        print(f"  recorded {target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target}")

    return record


# ------------------------------------------------------------------- gathering

def gather(cfg: Config, *, offline: bool, record: bool) -> tuple[SourceResult, SourceResult, SourceResult]:
    recorder = _make_recorder(record)

    if offline:
        portfolio = trading212.from_payloads(
            _load_fixture("trading212_positions.json"),
            _load_fixture("trading212_account_summary.json"),
        )
    elif cfg.has_trading212:
        client = trading212.Trading212Client(
            cfg.t212_api_key, cfg.t212_api_secret, cfg.t212_env, recorder=recorder
        )
        portfolio = client.fetch()
    else:
        portfolio = SourceResult.failure("trading212", "T212_API_KEY / T212_API_SECRET not set")

    tickers, names = [], []
    if portfolio.ok and portfolio.data:
        tickers = [p.ticker for p in portfolio.data.positions]
        names = [p.name for p in portfolio.data.positions if p.name]

    if offline:
        news = finlight.from_payload(
            _load_fixture("finlight_articles.json"),
            tickers=tickers,
            names=names,
            limit=cfg.news_limit,
        )
    elif cfg.has_finlight:
        news = finlight.fetch(
            cfg.finlight_api_key,
            tickers=tickers,
            names=names,
            limit=cfg.news_limit,
            recorder=recorder,
        )
    else:
        news = SourceResult.failure("finlight", "FINLIGHT_API_KEY not set")

    if offline:
        congress = congress_source.from_payload(_load_fixture("congress_trades.json"))
    else:
        congress = congress_source.fetch(cfg.congress_provider)

    return portfolio, news, congress


# ---------------------------------------------------------------- subcommands

def cmd_doctor(args: argparse.Namespace, cfg: Config) -> int:
    print(f"jarvis {__version__} — doctor\n")
    print("Configuration")
    for label, ok, detail in cfg.status_rows():
        print(f"  {OK if ok else BAD} {label:20} {detail}")
    for warning in cfg.warnings:
        print(f"  ! {warning}")

    print(f"\nState directory: {STATE_DIR}")
    previous = load_previous(STATE_DIR, today_iso())
    print(f"  previous snapshot: {previous['date'] if previous else 'none yet (first run will have no diff)'}")

    if args.offline:
        print("\n(--offline: skipping live calls)")
        return 0

    print("\nLive checks")
    if cfg.has_trading212:
        client = trading212.Trading212Client(
            cfg.t212_api_key, cfg.t212_api_secret, cfg.t212_env, recorder=_make_recorder(args.record)
        )
        result = client.fetch()
        if result.ok:
            count = len(result.data.positions)
            print(f"  {OK} trading212 ({cfg.t212_env}): {count} positions, "
                  f"{result.data.account.current_value:,.2f} {result.data.account.currency}")
            for key, value in (result.meta.get("positions_rate_limit") or {}).items():
                print(f"      {key}: {value}")
            for warning in result.warnings:
                print(f"      ! {warning}")
        else:
            print(f"  {BAD} trading212: {result.error}")
    else:
        print(f"  - trading212: skipped, keys not set")

    if cfg.has_finlight:
        result = finlight.fetch(cfg.finlight_api_key, limit=5, recorder=_make_recorder(args.record))
        if result.ok:
            print(f"  {OK} finlight: {result.meta.get('fetched')} articles fetched")
        else:
            print(f"  {BAD} finlight: {result.error}")
    else:
        print(f"  - finlight: skipped, key not set")

    congress = congress_source.fetch(cfg.congress_provider)
    print(f"  - congress: {congress.error}")

    print(f"  - email: {'configured for ' + cfg.email_to if cfg.has_email else 'not configured'}")
    print("\nNothing above sent an email or called Claude.")
    return 0


def cmd_snapshot(args: argparse.Namespace, cfg: Config) -> int:
    portfolio, _, _ = gather(cfg, offline=args.offline, record=args.record)
    if not portfolio.ok:
        print(f"{BAD} cannot snapshot: {portfolio.error}", file=sys.stderr)
        return 1
    snapshot = build_snapshot(portfolio.data, today_iso())
    path = save_snapshot(STATE_DIR, snapshot)
    print(f"{OK} saved {len(portfolio.data.positions)} positions to {path}")
    return 0


def cmd_brief(args: argparse.Namespace, cfg: Config) -> int:
    today = today_iso()
    portfolio, news, congress = gather(cfg, offline=args.offline, record=args.record)

    previous = load_previous(STATE_DIR, today)
    if portfolio.ok and portfolio.data:
        snapshot = build_snapshot(portfolio.data, today)
        diff = diff_snapshots(snapshot, previous, move_pct=cfg.move_pct, move_abs=cfg.move_abs)
        if not args.no_snapshot:
            save_snapshot(STATE_DIR, snapshot)
    else:
        diff = diff_snapshots({"positions": [], "account": {}}, previous, move_pct=cfg.move_pct, move_abs=cfg.move_abs)

    bundle = build_bundle(today=today, portfolio=portfolio, news=news, congress=congress, diff=diff)

    if args.dry_run:
        print(bundle.text)
        print("\n" + "-" * 70)
        print(f"[dry run] {len(bundle.text):,} characters ≈ {len(bundle.text) // 4:,} tokens. "
              "No Claude call, no email.")
        for note in bundle.source_notes:
            print(f"[dry run] note: {note}")
        return 0

    if not cfg.has_claude:
        print(f"{BAD} ANTHROPIC_API_KEY is not set — run with --dry-run to see the assembled input.",
              file=sys.stderr)
        return 1

    try:
        response = generate_brief(
            system_prompt=build_system_prompt(),
            user_content=bundle.text,
            api_key=cfg.anthropic_api_key,
            model=cfg.model,
            effort=cfg.effort,
        )
    except ClaudeError as exc:
        print(f"{BAD} {exc}", file=sys.stderr)
        return 1

    footer = list(bundle.source_notes) + list(response.notes)
    markdown = render_markdown(response.brief, date=today, footer_notes=footer)

    briefs_dir = STATE_DIR / "briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    brief_path = briefs_dir / f"{today}.md"
    brief_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print("-" * 70)
    print(
        f"{response.model} | {response.input_tokens:,} in / {response.output_tokens:,} out "
        f"≈ ${response.estimated_cost_usd:.3f} | saved {brief_path}"
    )

    if args.no_send:
        print("(--no-send: not emailed)")
        return 0
    if not cfg.has_email:
        print("(email not configured — set SMTP_* and EMAIL_TO to have this delivered)")
        return 0

    try:
        email_delivery.send(
            host=cfg.smtp_host,
            port=cfg.smtp_port,
            user=cfg.smtp_user,
            password=cfg.smtp_pass,
            sender=cfg.sender,
            to=cfg.email_to,
            subject=email_delivery.subject_for(today, response.brief),
            markdown=markdown,
        )
    except email_delivery.EmailError as exc:
        print(f"{BAD} {exc}", file=sys.stderr)
        return 1
    print(f"{OK} emailed to {cfg.email_to}")
    return 0


# ------------------------------------------------------------------------ main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="A daily portfolio brief.")
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    sub = parser.add_subparsers(dest="command")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--offline", action="store_true", help="use bundled fixtures, make no network calls")
        p.add_argument("--record", action="store_true", help="dump raw API payloads to fixtures/live/")

    doctor = sub.add_parser("doctor", help="check configuration and reachability")
    common(doctor)
    doctor.set_defaults(func=cmd_doctor)

    brief = sub.add_parser("brief", help="produce (and email) today's brief")
    common(brief)
    brief.add_argument("--dry-run", action="store_true", help="print the assembled model input and stop")
    brief.add_argument("--no-send", action="store_true", help="print the brief instead of emailing it")
    brief.add_argument("--no-snapshot", action="store_true", help="do not write today's snapshot")
    brief.set_defaults(func=cmd_brief)

    snapshot = sub.add_parser("snapshot", help="save today's positions without briefing")
    common(snapshot)
    snapshot.set_defaults(func=cmd_snapshot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args, Config.from_env())


if __name__ == "__main__":
    raise SystemExit(main())
