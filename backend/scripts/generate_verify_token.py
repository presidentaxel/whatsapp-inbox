"""
Utility to manage the WHATSAPP_VERIFY_TOKEN stored in backend/.env

Usage:
    python scripts/generate_verify_token.py          # create token if missing
    python scripts/generate_verify_token.py --force  # overwrite existing token
"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path
from typing import Dict

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
KEY_NAME = "WHATSAPP_VERIFY_TOKEN"


def read_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(path: Path, values: Dict[str, str]) -> None:
    lines = []
    existing_keys = set()
    if path.exists():
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                existing_keys.add(key)
                if key in values:
                    lines.append(f"{key}={values[key]}")
                    continue
            lines.append(line)

    for key, value in values.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n")


def generate_token(length: int = 32) -> str:
    # urlsafe pour éviter les caractères problématiques dans l’UI Meta
    return secrets.token_urlsafe(length)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage WhatsApp webhook verify token")
    parser.add_argument("--force", action="store_true", help="overwrite existing token")
    parser.add_argument("--length", type=int, default=32, help="token length (default: 32)")
    args = parser.parse_args()

    env_values = read_env(ENV_PATH)

    if KEY_NAME in env_values and not args.force:
        existing = env_values[KEY_NAME]
        print(f"{KEY_NAME} already present in {ENV_PATH}")
        print(f"Current value: {existing}")
        print("Use --force to overwrite it.")
        print(f"TOKEN={existing}")
        return

    token = generate_token(args.length)
    env_values[KEY_NAME] = token
    write_env(ENV_PATH, env_values)

    print(f"{KEY_NAME} set to: {token}")
    print(f"Stored in {ENV_PATH}")
    print("Use this value in the Meta dashboard when verifying the webhook.")
    print(f"TOKEN={token}")


if __name__ == "__main__":
    main()

