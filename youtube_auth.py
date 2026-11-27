"""One-time interactive YouTube OAuth 2.0 login.

    .venv\\Scripts\\python youtube_auth.py

1. Google Cloud Console -> APIs & Services -> YouTube Data API v3 ni yoqing.
2. Credentials -> OAuth 2.0 Client ID (Desktop app) yarating va JSON faylni yuklab oling.
3. Faylni data/youtube_client_secret.json sifatida saqlang.
4. Shu skriptni ishga tushiring — brauzerda Google akkauntingiz bilan tasdiqlang.
"""
from app.channels.youtube import SCOPES
from app.config import env


def main() -> None:
    if not env.yt_secrets_path.exists():
        print(f"❌ Fayl topilmadi: {env.yt_secrets_path}")
        print("Google Cloud Console -> OAuth 2.0 Client ID (Desktop app) JSON faylini shu joyga qo'ying.")
        return
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(env.yt_secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)
    env.yt_token_path.parent.mkdir(parents=True, exist_ok=True)
    env.yt_token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"✅ YouTube tokeni saqlandi: {env.yt_token_path}")
    print("Endi agentni ishga tushiring:  .venv\\Scripts\\python run.py")


if __name__ == "__main__":
    main()
