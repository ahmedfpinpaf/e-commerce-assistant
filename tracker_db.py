import sqlite3
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.db")

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Tracked products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_products (
                id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                brand TEXT,
                model TEXT,
                product_url TEXT NOT NULL UNIQUE,
                website TEXT NOT NULL,
                image_url TEXT,
                current_price REAL NOT NULL,
                previous_price REAL,
                currency TEXT NOT NULL DEFAULT 'PKR',
                target_price REAL,
                tracking_status TEXT NOT NULL DEFAULT 'active',
                alert_type TEXT NOT NULL DEFAULT 'target_price',
                last_checked REAL,
                last_price_change REAL,
                last_alert_sent REAL,
                last_alert_price REAL,
                specifications TEXT,
                created_at REAL NOT NULL
            )
        """)
        
        # 2. Price history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES tracked_products(id) ON DELETE CASCADE
            )
        """)
        
        # 3. User settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # 4. Alert log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                previous_price REAL,
                current_price REAL NOT NULL,
                target_price REAL,
                currency TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sent_at REAL NOT NULL,
                status TEXT NOT NULL
            )
        """)
        
        # Default user email setting if not present
        cursor.execute("SELECT value FROM user_settings WHERE key = 'alert_email'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO user_settings (key, value) VALUES ('alert_email', 'user@example.com')")
            cursor.execute("INSERT INTO user_settings (key, value) VALUES ('check_interval_minutes', '15')")
            cursor.execute("INSERT INTO user_settings (key, value) VALUES ('notifications_enabled', 'true')")
            
        conn.commit()

# Product CRUD
def add_tracked_product(
    product_name: str,
    product_url: str,
    website: str,
    current_price: float,
    currency: str = "PKR",
    brand: Optional[str] = None,
    model: Optional[str] = None,
    image_url: Optional[str] = None,
    target_price: Optional[float] = None,
    alert_type: str = "target_price",
    specifications: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    now = time.time()
    prod_id = str(uuid.uuid4())
    specs_json = json.dumps(specifications or {})
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if URL already tracked
        cursor.execute("SELECT id FROM tracked_products WHERE product_url = ?", (product_url,))
        existing = cursor.fetchone()
        if existing:
            # Update existing product target price / current price
            cursor.execute("""
                UPDATE tracked_products
                SET current_price = ?, target_price = COALESCE(?, target_price),
                    alert_type = COALESCE(?, alert_type), tracking_status = 'active',
                    last_checked = ?
                WHERE id = ?
            """, (current_price, target_price, alert_type, now, existing["id"]))
            conn.commit()
            return get_tracked_product(existing["id"])
        
        cursor.execute("""
            INSERT INTO tracked_products (
                id, product_name, brand, model, product_url, website, image_url,
                current_price, previous_price, currency, target_price,
                tracking_status, alert_type, last_checked, last_price_change,
                last_alert_sent, specifications, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prod_id, product_name, brand or "N/A", model or "N/A", product_url, website,
            image_url or "", current_price, current_price, currency, target_price,
            "active", alert_type, now, now, None, specs_json, now
        ))
        
        # Initial price history entry
        cursor.execute("""
            INSERT INTO price_history (product_id, price, currency, timestamp)
            VALUES (?, ?, ?, ?)
        """, (prod_id, current_price, currency, now))
        
        conn.commit()
        
    return get_tracked_product(prod_id)

def get_tracked_product(prod_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracked_products WHERE id = ?", (prod_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

def get_all_tracked_products() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracked_products ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def update_tracked_product(
    prod_id: str,
    target_price: Optional[float] = None,
    tracking_status: Optional[str] = None,
    alert_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        updates = []
        params = []
        
        if target_price is not None:
            updates.append("target_price = ?")
            params.append(target_price)
        if tracking_status is not None:
            updates.append("tracking_status = ?")
            params.append(tracking_status)
        if alert_type is not None:
            updates.append("alert_type = ?")
            params.append(alert_type)
            
        if not updates:
            return get_tracked_product(prod_id)
            
        params.append(prod_id)
        cursor.execute(f"UPDATE tracked_products SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        
    return get_tracked_product(prod_id)

def delete_tracked_product(prod_id: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tracked_products WHERE id = ?", (prod_id,))
        cursor.execute("DELETE FROM price_history WHERE product_id = ?", (prod_id,))
        conn.commit()
        return cursor.rowcount > 0

def record_price_update(
    prod_id: str,
    new_price: float,
    currency: Optional[str] = None
) -> Dict[str, Any]:
    now = time.time()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT current_price, currency FROM tracked_products WHERE id = ?", (prod_id,))
        row = cursor.fetchone()
        if not row:
            return {}
            
        old_price = row["current_price"]
        curr = currency or row["currency"]
        price_changed = abs(new_price - old_price) > 0.01
        
        if price_changed:
            cursor.execute("""
                UPDATE tracked_products
                SET previous_price = current_price,
                    current_price = ?,
                    currency = ?,
                    last_checked = ?,
                    last_price_change = ?
                WHERE id = ?
            """, (new_price, curr, now, now, prod_id))
            
            # Record in history
            cursor.execute("""
                INSERT INTO price_history (product_id, price, currency, timestamp)
                VALUES (?, ?, ?, ?)
            """, (prod_id, new_price, curr, now))
        else:
            cursor.execute("""
                UPDATE tracked_products
                SET last_checked = ?
                WHERE id = ?
            """, (now, prod_id))
            
        conn.commit()
        
    return get_tracked_product(prod_id)

def record_alert_sent(prod_id: str, price: float, alert_type: str, recipient_email: str, subject: str, body: str):
    now = time.time()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tracked_products
            SET last_alert_sent = ?,
                last_alert_price = ?,
                tracking_status = 'alert_triggered'
            WHERE id = ?
        """, (now, price, prod_id))
        
        cursor.execute("SELECT product_name, previous_price, target_price, currency FROM tracked_products WHERE id = ?", (prod_id,))
        row = cursor.fetchone()
        
        cursor.execute("""
            INSERT INTO alert_logs (
                product_id, product_name, alert_type, previous_price, current_price,
                target_price, currency, recipient_email, subject, body, sent_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prod_id,
            row["product_name"] if row else "Unknown",
            alert_type,
            row["previous_price"] if row else price,
            price,
            row["target_price"] if row else None,
            row["currency"] if row else "PKR",
            recipient_email,
            subject,
            body,
            now,
            "sent"
        ))
        conn.commit()

def get_price_history(prod_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM price_history WHERE product_id = ? ORDER BY timestamp ASC", (prod_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_alert_logs(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alert_logs ORDER BY sent_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# Settings CRUD
def get_user_settings() -> Dict[str, str]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM user_settings")
        return {r["key"]: r["value"] for r in cursor.fetchall()}

def update_user_settings(settings: Dict[str, str]):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for k, v in settings.items():
            cursor.execute("""
                INSERT INTO user_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (k, str(v)))
        conn.commit()

# Initialize DB when module loaded
init_db()
