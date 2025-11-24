import argparse
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def load_env():
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)


def persist_env_var(key: str, value: str):
    """Replace or append KEY=value in backend/.env."""
    lines = []
    if ENV_FILE.exists():
        with ENV_FILE.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()

    key_line = f"{key}="
    replaced = False
    for idx, line in enumerate(lines):
        if line.startswith(key_line):
            lines[idx] = f"{key}={value}\n"
            replaced = True
            break

    if not replaced:
        lines.append(f"{key}={value}\n")

    with ENV_FILE.open("w", encoding="utf-8") as fh:
        fh.writelines(lines)


def refresh_token(app_id: str, app_secret: str, short_token: str) -> dict:
    url = "https://graph.facebook.com/v19.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def update_supabase(new_token: str):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("⚠️  SUPABASE_URL / SUPABASE_KEY non définis, skip update DB.")
        return

    client = create_client(supabase_url, supabase_key)
    default_slug = os.getenv("DEFAULT_ACCOUNT_SLUG", "default-env-account")

    accounts = (
        client.table("whatsapp_accounts")
        .select("id")
        .eq("slug", default_slug)
        .limit(1)
        .execute()
    )
    if accounts.data:
        account_id = accounts.data[0]["id"]
        client.table("whatsapp_accounts").update({"access_token": new_token}).eq("id", account_id).execute()
        print(f"✅ Supabase: access_token mis à jour pour {default_slug}")
    else:
        print("⚠️  Aucun compte 'default-env-account' trouvé, skip update DB.")


def main():
    parser = argparse.ArgumentParser(description="Échange un token WhatsApp court contre un token long-lived.")
    parser.add_argument("--token", help="Token court (override de WHATSAPP_TOKEN)")
    args = parser.parse_args()

    load_env()

    app_id = os.getenv("META_APP_ID")
    app_secret = os.getenv("META_APP_SECRET")
    short_token = args.token or os.getenv("WHATSAPP_TOKEN")

    if not all([app_id, app_secret, short_token]):
        raise SystemExit(
            "META_APP_ID, META_APP_SECRET et WHATSAPP_TOKEN doivent être définis (ou passés en argument)."
        )

    print("⏳ Échange du token court contre un token long-lived…")
    payload = refresh_token(app_id, app_secret, short_token)
    new_token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if not new_token:
        raise SystemExit("Impossible d'obtenir un nouveau token (payload incomplet).")

    persist_env_var("WHATSAPP_TOKEN", new_token)
    update_supabase(new_token)

    print("✅ Nouveau token enregistré dans backend/.env (WHATSAPP_TOKEN).")
    if expires_in:
        print(f"ℹ️  expires_in ≈ {int(expires_in) / 3600:.1f} heures")


if __name__ == "__main__":
    main()

