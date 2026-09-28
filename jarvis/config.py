"""Configuration: a tiny .env loader plus validation.

Deliberately dependency-free. Secrets are never logged or printed — the only
thing reported about a secret is whether it is set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
STATE_DIR = PACKAGE_DIR / "state"
FIXTURES_DIR = PACKAGE_DIR / "fixtures"
LIVE_FIXTURES_DIR = FIXTURES_DIR / "live"


def load_dotenv(*paths: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overwriting what is already set.

    cron does not inherit a shell profile, which is the whole reason this exists.
    """
    candidates = paths or (PACKAGE_DIR / ".env", REPO_DIR / ".env")
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass
class Config:
    t212_api_key: str = ""
    t212_api_secret: str = ""
    t212_env: str = "live"
    finlight_api_key: str = ""
    anthropic_api_key: str = ""
    model: str = "claude-fable-5-1"
    effort: str = "medium"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    email_to: str = ""
    email_from: str = ""
    move_pct: float = 2.0
    move_abs: float = 50.0
    news_limit: int = 40
    congress_provider: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        cfg = cls(
            t212_api_key=os.environ.get("T212_API_KEY", "").strip(),
            t212_api_secret=os.environ.get("T212_API_SECRET", "").strip(),
            t212_env=(os.environ.get("T212_ENV", "live").strip().lower() or "live"),
            finlight_api_key=os.environ.get("FINLIGHT_API_KEY", "").strip(),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            model=os.environ.get("JARVIS_MODEL", "claude-fable-5-1").strip(),
            effort=os.environ.get("JARVIS_EFFORT", "medium").strip(),
            smtp_host=os.environ.get("SMTP_HOST", "").strip(),
            smtp_port=_int("SMTP_PORT", 587),
            smtp_user=os.environ.get("SMTP_USER", "").strip(),
            smtp_pass=os.environ.get("SMTP_PASS", ""),
            email_to=os.environ.get("EMAIL_TO", "").strip(),
            email_from=os.environ.get("EMAIL_FROM", "").strip(),
            move_pct=_float("JARVIS_MOVE_PCT", 2.0),
            move_abs=_float("JARVIS_MOVE_ABS", 50.0),
            news_limit=_int("JARVIS_NEWS_LIMIT", 40),
            congress_provider=os.environ.get("JARVIS_CONGRESS_PROVIDER", "").strip(),
        )
        if cfg.t212_env not in ("live", "demo"):
            cfg.warnings.append(f"T212_ENV={cfg.t212_env!r} is not live/demo; using live")
            cfg.t212_env = "live"
        return cfg

    # --- capability checks: each answers "can this part run?" ---------------

    @property
    def has_trading212(self) -> bool:
        return bool(self.t212_api_key and self.t212_api_secret)

    @property
    def has_finlight(self) -> bool:
        return bool(self.finlight_api_key)

    @property
    def has_claude(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_email(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_pass and self.email_to)

    @property
    def sender(self) -> str:
        return self.email_from or self.smtp_user

    def status_rows(self) -> list[tuple[str, bool, str]]:
        """(label, ok, detail) — detail never contains a secret."""
        return [
            ("T212_API_KEY", bool(self.t212_api_key), "set" if self.t212_api_key else "missing"),
            ("T212_API_SECRET", bool(self.t212_api_secret), "set" if self.t212_api_secret else "missing"),
            ("T212_ENV", True, self.t212_env),
            ("FINLIGHT_API_KEY", self.has_finlight, "set" if self.has_finlight else "missing"),
            ("ANTHROPIC_API_KEY", self.has_claude, "set" if self.has_claude else "missing"),
            ("model", True, self.model),
            ("effort", True, self.effort),
            ("email", self.has_email, self.email_to if self.has_email else "not configured"),
        ]
