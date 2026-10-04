"""Local single-user authentication helpers.

Credentials are stored outside source control and passwords are derived with
PBKDF2-HMAC-SHA256. This is intended for a private single-user deployment;
multi-user or internet-facing deployments should use an identity provider.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import getpass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ITERATIONS = 600_000


class LocalAuthStore:
    """Persist one local account and the cookie-signing secret."""

    def __init__(self, account_path: str, secret_path: str, username: str = "AtharvaKh",
                 password_hash: str | None = None, password_salt: str | None = None,
                 password_iterations: int = ITERATIONS) -> None:
        self.account_path = Path(account_path)
        self.secret_path = Path(secret_path)
        self.username = username
        self.password_hash = password_hash
        self.password_salt = password_salt
        self.password_iterations = password_iterations

    def _prepare(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def session_secret(self, configured_secret: str | None = None) -> str:
        if configured_secret:
            return configured_secret
        self._prepare(self.secret_path)
        if not self.secret_path.exists():
            self._write_private(self.secret_path, secrets.token_urlsafe(48))
        return self.secret_path.read_text(encoding="utf-8").strip()

    def account(self) -> dict[str, Any] | None:
        # Serverless deployments can supply the existing one-way verifier as
        # secret environment values instead of relying on ephemeral disk.
        if self.password_hash and self.password_salt:
            return {"username": self.username, "salt": self.password_salt,
                    "password_hash": self.password_hash, "iterations": self.password_iterations}
        if not self.account_path.exists():
            return None
        try:
            data = json.loads(self.account_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and data.get("username") else None
        except (OSError, json.JSONDecodeError):
            return None

    def create_account(self, username: str, password: str) -> bool:
        if self.account() is not None:
            return False
        self._prepare(self.account_path)
        # Exclusive file creation makes setup one-time even across simultaneous requests.
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
        record = {"username": username, "salt": salt.hex(), "password_hash": digest.hex(),
                  "iterations": ITERATIONS, "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            descriptor = os.open(self.account_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream)
        return True

    def verify(self, username: str, password: str) -> bool:
        account = self.account()
        if not account or not hmac.compare_digest(str(account.get("username", "")), username):
            # Do a dummy derivation for missing users to reduce timing differences.
            hashlib.pbkdf2_hmac("sha256", password.encode(), b"marketdesk-dummy", ITERATIONS)
            return False
        try:
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(account["salt"]),
                                         int(account.get("iterations", ITERATIONS)))
            return hmac.compare_digest(actual.hex(), str(account["password_hash"]))
        except (KeyError, ValueError, TypeError):
            return False

    @staticmethod
    def _write_private(path: Path, value: str) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)


def validate_credentials(username: str, password: str, allowed_username: str = "AtharvaKh") -> str | None:
    """Return a user-safe validation message or None when acceptable."""
    if not hmac.compare_digest(username.strip(), allowed_username):
        return f"This private workspace only allows the {allowed_username} account."
    if len(password) < 12:
        return "Use a password with at least 12 characters."
    if len(password) > 256:
        return "Password must be 256 characters or fewer."
    return None


def derive_password_verifier(password: str, iterations: int = ITERATIONS) -> tuple[str, str]:
    """Create a salted PBKDF2 verifier suitable for serverless secret settings."""
    if not 600_000 <= iterations <= 2_000_000:
        raise ValueError("Password hash iterations must be between 600000 and 2000000.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return salt.hex(), digest.hex()


if __name__ == "__main__":
    print("Generate a salted PBKDF2-HMAC-SHA256 verifier for a private deployment.")
    password = getpass.getpass("Admin password (input hidden): ")
    confirmation = getpass.getpass("Confirm admin password: ")
    if not password or not hmac.compare_digest(password, confirmation):
        raise SystemExit("Passwords were empty or did not match.")
    salt, password_hash = derive_password_verifier(password)
    print("Set these as private API host environment variables (never commit them):")
    print(f"AUTH_PASSWORD_SALT={salt}")
    print(f"AUTH_PASSWORD_HASH={password_hash}")
    print(f"AUTH_PASSWORD_ITERATIONS={ITERATIONS}")
