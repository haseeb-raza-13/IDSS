import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Users stored in a lightweight SQLite table separate from the pipeline DB
_AUTH_DB = settings.db_path.parent / "idss_auth.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_AUTH_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id   TEXT PRIMARY KEY,
            email     TEXT UNIQUE NOT NULL,
            name      TEXT NOT NULL,
            hashed_pw TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return _pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return _pwd_context.verify(plain, hashed)

    @staticmethod
    def create_access_token(payload: dict) -> str:
        data = payload.copy()
        data["exp"] = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
        data["type"] = "access"
        return jwt.encode(data, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def create_refresh_token(payload: dict) -> str:
        data = payload.copy()
        data["exp"] = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )
        data["type"] = "refresh"
        return jwt.encode(data, settings.secret_key, algorithm=settings.algorithm)

    @staticmethod
    def decode_access_token(token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None

    @staticmethod
    def decode_refresh_token(token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            if payload.get("type") != "refresh":
                return None
            return payload
        except JWTError:
            return None

    @classmethod
    def register(cls, email: str, password: str, name: str) -> dict:
        conn = _get_conn()
        existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            raise ValueError("Email already registered")
        user_id = str(uuid.uuid4())
        hashed = cls.hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO users (user_id, email, name, hashed_pw, created_at) VALUES (?,?,?,?,?)",
            (user_id, email, name, hashed, now),
        )
        conn.commit()
        conn.close()
        return {"user_id": user_id, "email": email, "name": name}

    @classmethod
    def login(cls, email: str, password: str) -> Optional[dict]:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if not row or not cls.verify_password(password, row["hashed_pw"]):
            return None
        return {"user_id": row["user_id"], "email": row["email"], "name": row["name"]}
