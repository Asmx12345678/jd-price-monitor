import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


class Storage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._init()

    def _connect(self):
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    image_url TEXT,
                    product_url TEXT NOT NULL,
                    coupon_url TEXT,
                    current_price REAL NOT NULL,
                    base_price REAL,
                    unit_price REAL,
                    unit_label TEXT,
                    pack_label TEXT,
                    offer_text TEXT,
                    captured_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_snapshot_sku_time
                ON snapshots(sku_id, captured_at DESC);

                CREATE TABLE IF NOT EXISTS deals (
                    sku_id TEXT PRIMARY KEY,
                    reference_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    drop_percent REAL NOT NULL,
                    reason TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_candidates (
                    sku_id TEXT PRIMARY KEY,
                    comparison_kind TEXT NOT NULL,
                    reference_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    reference_unit_price REAL,
                    drop_percent REAL NOT NULL,
                    confirmations INTEGER NOT NULL DEFAULT 1,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(deals)")}
            if "comparison_kind" not in columns:
                conn.execute("ALTER TABLE deals ADD COLUMN comparison_kind TEXT NOT NULL DEFAULT 'total_price'")
            if "reference_unit_price" not in columns:
                conn.execute("ALTER TABLE deals ADD COLUMN reference_unit_price REAL")
            for name, declaration in (
                ("deal_kind", "TEXT NOT NULL DEFAULT 'legacy'"),
                ("public_discount_percent", "REAL NOT NULL DEFAULT 0"),
                ("historical_drop_percent", "REAL NOT NULL DEFAULT 0"),
                ("confidence", "TEXT NOT NULL DEFAULT 'conditional'"),
                ("confirmation_count", "INTEGER NOT NULL DEFAULT 1"),
            ):
                if name not in columns:
                    conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {declaration}")
            snapshot_columns = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)")}
            if "unit_key" not in snapshot_columns:
                conn.execute("ALTER TABLE snapshots ADD COLUMN unit_key TEXT")
            for name, kind in (
                ("price_type", "TEXT"), ("coupon_discount", "REAL"), ("coupon_quota", "REAL")
            ):
                if name not in snapshot_columns:
                    conn.execute(f"ALTER TABLE snapshots ADD COLUMN {name} {kind}")

    def previous_price(self, sku_id: str) -> Optional[float]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT current_price FROM snapshots WHERE sku_id=? ORDER BY id DESC LIMIT 1",
                (sku_id,),
            ).fetchone()
            return float(row[0]) if row else None

    def previous_snapshot(self, sku_id: str) -> Optional[Dict[str, object]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT current_price, base_price, unit_price, unit_label, unit_key, pack_label, "
                "price_type, offer_text, captured_at FROM snapshots "
                "WHERE sku_id=? ORDER BY id DESC LIMIT 1",
                (sku_id,),
            ).fetchone()
            return dict(row) if row else None

    def add_snapshot(self, item: Dict[str, object]) -> None:
        fields = [
            "sku_id", "name", "category", "source", "image_url", "product_url",
            "coupon_url", "current_price", "base_price", "unit_price", "unit_label",
            "unit_key", "pack_label", "offer_text", "captured_at", "price_type",
            "coupon_discount", "coupon_quota",
        ]
        values = [item.get(field) for field in fields]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"INSERT INTO snapshots ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                values,
            )

    def upsert_deal(
        self, sku_id: str, reference: float, current: float, drop: float, reason: str,
        comparison_kind: str = "total_price", reference_unit_price: Optional[float] = None,
        deal_kind: str = "historical_drop", public_discount_percent: float = 0,
        historical_drop_percent: float = 0, confidence: str = "high",
        confirmation_count: int = 1,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO deals(
                    sku_id, reference_price, current_price, drop_percent, reason, detected_at,
                    active, comparison_kind, reference_unit_price, deal_kind,
                    public_discount_percent, historical_drop_percent, confidence,
                    confirmation_count
                ) VALUES(?,?,?,?,?,?,1,?,?,?,?,?,?,?)
                ON CONFLICT(sku_id) DO UPDATE SET
                    reference_price=excluded.reference_price,
                    current_price=excluded.current_price,
                    drop_percent=excluded.drop_percent,
                    reason=excluded.reason,
                    detected_at=excluded.detected_at,
                    comparison_kind=excluded.comparison_kind,
                    reference_unit_price=excluded.reference_unit_price,
                    deal_kind=excluded.deal_kind,
                    public_discount_percent=excluded.public_discount_percent,
                    historical_drop_percent=excluded.historical_drop_percent,
                    confidence=excluded.confidence,
                    confirmation_count=excluded.confirmation_count,
                    active=1
                """,
                (
                    sku_id, reference, current, drop, reason, now, comparison_kind,
                    reference_unit_price, deal_kind, public_discount_percent,
                    historical_drop_percent, confidence, confirmation_count,
                ),
            )

    def candidate(self, sku_id: str) -> Optional[Dict[str, object]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM price_candidates WHERE sku_id=?", (sku_id,)).fetchone()
            return dict(row) if row else None

    def confirm_candidate(
        self, sku_id: str, comparison_kind: str, reference: float, current: float,
        drop: float, reference_unit_price: Optional[float] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT * FROM price_candidates WHERE sku_id=?", (sku_id,)).fetchone()
            same = existing and existing["comparison_kind"] == comparison_kind and abs(
                float(existing["current_price"]) - current
            ) < 0.01
            confirmations = int(existing["confirmations"]) + 1 if same else 1
            conn.execute(
                """
                INSERT INTO price_candidates(
                    sku_id, comparison_kind, reference_price, current_price,
                    reference_unit_price, drop_percent, confirmations, first_seen, last_seen
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(sku_id) DO UPDATE SET
                    comparison_kind=excluded.comparison_kind,
                    reference_price=excluded.reference_price,
                    current_price=excluded.current_price,
                    reference_unit_price=excluded.reference_unit_price,
                    drop_percent=excluded.drop_percent,
                    confirmations=excluded.confirmations,
                    first_seen=CASE WHEN price_candidates.current_price=excluded.current_price
                                    THEN price_candidates.first_seen ELSE excluded.first_seen END,
                    last_seen=excluded.last_seen
                """,
                (
                    sku_id, comparison_kind, reference, current, reference_unit_price,
                    drop, confirmations, now, now,
                ),
            )
            return confirmations

    def clear_candidate(self, sku_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM price_candidates WHERE sku_id=?", (sku_id,))

    def deactivate_legacy_deals(self) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("UPDATE deals SET active=0 WHERE active=1 AND deal_kind='legacy'")
            return cursor.rowcount

    def deactivate(self, sku_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE deals SET active=0 WHERE sku_id=?", (sku_id,))

    def active_deal(self, sku_id: str) -> Optional[Dict[str, object]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM deals WHERE sku_id=? AND active=1", (sku_id,)
            ).fetchone()
            return dict(row) if row else None

    def deactivate_missing(self, sku_ids) -> None:
        sku_ids = list(sku_ids)
        with self._lock, self._connect() as conn:
            if not sku_ids:
                conn.execute("UPDATE deals SET active=0")
                return
            placeholders = ",".join("?" for _ in sku_ids)
            conn.execute(
                f"UPDATE deals SET active=0 WHERE sku_id NOT IN ({placeholders})",
                sku_ids,
            )

    def deactivate_stale(self, hours: int = 24) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE deals SET active=0 WHERE detected_at < ?", (cutoff,))

    def deactivate_unit_price_deals(self) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("UPDATE deals SET active=0 WHERE active=1 AND comparison_kind='unit_price'")
            return cursor.rowcount

    def deals(self) -> List[Dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*, s.name, s.category, s.source, s.image_url, s.product_url,
                       s.coupon_url, s.unit_price, s.unit_label, s.pack_label,
                       s.unit_key, s.offer_text, s.captured_at, s.price_type,
                       s.coupon_discount, s.coupon_quota
                FROM deals d
                JOIN snapshots s ON s.id=(
                    SELECT id FROM snapshots WHERE sku_id=d.sku_id ORDER BY id DESC LIMIT 1
                )
                WHERE d.active=1
                ORDER BY d.drop_percent DESC, d.detected_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def set_state(self, key: str, value: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_state(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def snapshot_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])

    def tracked_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(DISTINCT sku_id) FROM snapshots").fetchone()[0])

