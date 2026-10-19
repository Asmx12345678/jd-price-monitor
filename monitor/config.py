from dataclasses import dataclass
import os
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    app_key: str
    app_secret: str
    site_id: str
    position_id: str
    mode: str
    scan_interval_minutes: int
    discovery_pages: int
    drop_threshold_percent: float
    host: str
    port: int
    root: Path
    database_path: Path
    public_read_only: bool

    @classmethod
    def from_env(cls, root: Path) -> "Settings":
        load_dotenv(root / ".env")
        mode = os.getenv("JD_MODE", "demo").lower()
        if mode not in {"demo", "live"}:
            mode = "demo"
        return cls(
            app_key=os.getenv("JD_APP_KEY", "").strip(),
            app_secret=os.getenv("JD_APP_SECRET", "").strip(),
            site_id=os.getenv("JD_SITE_ID", "").strip(),
            position_id=os.getenv("JD_POSITION_ID", "").strip(),
            mode=mode,
            scan_interval_minutes=max(5, int(os.getenv("JD_SCAN_INTERVAL_MINUTES", "30"))),
            discovery_pages=max(5, min(50, int(os.getenv("JD_DISCOVERY_PAGES", "20")))),
            drop_threshold_percent=max(0, float(os.getenv("JD_DROP_THRESHOLD_PERCENT", "15"))),
            host=os.getenv("JD_HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", os.getenv("JD_PORT", "8765"))),
            root=root,
            database_path=Path(os.getenv("JD_DATABASE_PATH", str(root / "data" / "prices.db"))),
            public_read_only=os.getenv("JD_PUBLIC_READ_ONLY", "false").lower() in {"1", "true", "yes"},
        )

    @property
    def live_ready(self) -> bool:
        return self.mode == "live" and bool(self.app_key and self.app_secret)

