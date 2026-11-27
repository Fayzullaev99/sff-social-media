"""Environment (secrets) and runtime settings loading."""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "uploads").mkdir(exist_ok=True)
(DATA_DIR / "videos").mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")


def _int_list(raw: str) -> list[int]:
    out = []
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


@dataclass
class Env:
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    gemini_embed_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
    )
    tg_api_id: int = field(default_factory=lambda: int(os.getenv("TG_API_ID") or 0))
    tg_api_hash: str = field(default_factory=lambda: os.getenv("TG_API_HASH", ""))
    tg_session: str = field(default_factory=lambda: os.getenv("TG_SESSION", "data/userbot"))
    admin_bot_token: str = field(default_factory=lambda: os.getenv("ADMIN_BOT_TOKEN", ""))
    admin_ids: list[int] = field(default_factory=lambda: _int_list(os.getenv("ADMIN_IDS", "")))
    dashboard_host: str = field(default_factory=lambda: os.getenv("DASHBOARD_HOST", "127.0.0.1"))
    dashboard_port: int = field(default_factory=lambda: int(os.getenv("DASHBOARD_PORT") or 8080))
    dashboard_user: str = field(default_factory=lambda: os.getenv("DASHBOARD_USER", "admin"))
    dashboard_password: str = field(default_factory=lambda: os.getenv("DASHBOARD_PASSWORD", "change-me"))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'agent.db').as_posix()}")
    )
    # --- Video Factory ---
    pexels_api_key: str = field(default_factory=lambda: os.getenv("PEXELS_API_KEY", ""))
    gemini_veo_model: str = field(default_factory=lambda: os.getenv("GEMINI_VEO_MODEL", "veo-2.0-generate-001"))
    heygen_api_key: str = field(default_factory=lambda: os.getenv("HEYGEN_API_KEY", ""))
    heygen_avatar_id: str = field(default_factory=lambda: os.getenv("HEYGEN_AVATAR_ID", ""))
    public_media_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_MEDIA_BASE_URL", "").rstrip("/"))
    # --- YouTube ---
    yt_client_secrets: str = field(default_factory=lambda: os.getenv("YT_CLIENT_SECRETS", "data/youtube_client_secret.json"))
    yt_token_file: str = field(default_factory=lambda: os.getenv("YT_TOKEN_FILE", "data/youtube_token.json"))
    yt_default_privacy: str = field(default_factory=lambda: os.getenv("YT_DEFAULT_PRIVACY", "private"))
    # --- Instagram ---
    ig_access_token: str = field(default_factory=lambda: os.getenv("IG_ACCESS_TOKEN", ""))
    ig_account_id: str = field(default_factory=lambda: os.getenv("IG_ACCOUNT_ID", ""))
    # --- Ads (Targetolog) ---
    meta_ads_access_token: str = field(default_factory=lambda: os.getenv("META_ADS_ACCESS_TOKEN", ""))
    meta_ad_account_id: str = field(default_factory=lambda: os.getenv("META_AD_ACCOUNT_ID", ""))
    meta_page_id: str = field(default_factory=lambda: os.getenv("META_PAGE_ID", ""))
    google_ads_developer_token: str = field(default_factory=lambda: os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""))
    google_ads_customer_id: str = field(default_factory=lambda: os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""))
    google_ads_refresh_token: str = field(default_factory=lambda: os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""))
    google_ads_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_ADS_CLIENT_ID", ""))
    google_ads_client_secret: str = field(default_factory=lambda: os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""))

    @property
    def session_path(self) -> str:
        p = Path(self.tg_session)
        return str(p if p.is_absolute() else BASE_DIR / p)

    @property
    def yt_secrets_path(self) -> Path:
        p = Path(self.yt_client_secrets)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def yt_token_path(self) -> Path:
        p = Path(self.yt_token_file)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def telegram_configured(self) -> bool:
        return bool(self.tg_api_id and self.tg_api_hash)

    @property
    def admin_bot_configured(self) -> bool:
        return bool(self.admin_bot_token and self.admin_ids)

    @property
    def youtube_configured(self) -> bool:
        return self.yt_token_path.exists()

    @property
    def instagram_configured(self) -> bool:
        return bool(self.ig_access_token and self.ig_account_id)

    @property
    def meta_ads_configured(self) -> bool:
        return bool(self.meta_ads_access_token and self.meta_ad_account_id)

    @property
    def google_ads_configured(self) -> bool:
        return bool(
            self.google_ads_developer_token
            and self.google_ads_customer_id
            and self.google_ads_refresh_token
            and self.google_ads_client_id
            and self.google_ads_client_secret
        )


env = Env()


def load_default_settings() -> dict[str, Any]:
    path = BASE_DIR / "config" / "settings.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result
