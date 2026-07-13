"""在本機取得 YouTube OAuth refresh token（不會把 token 寫入檔案）。"""

from __future__ import annotations

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"缺少環境變數 {name}。請依 README 設定後再執行。")
    return value


def main() -> int:
    try:
        client_id = required_env("GOOGLE_CLIENT_ID")
        client_secret = required_env("GOOGLE_CLIENT_SECRET")
        config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(config, SCOPES)
        print("即將開啟瀏覽器。請登入擁有『半盞江湖』的 Google 帳號，並選擇該品牌頻道。")
        credentials = flow.run_local_server(
            host="localhost",
            port=0,
            open_browser=True,
            access_type="offline",
            prompt="consent",
        )

        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        response = youtube.channels().list(part="snippet", mine=True).execute()
        channels = response.get("items", [])
        if not channels:
            raise RuntimeError("此登入身分找不到 YouTube 頻道，可能選錯 Google 帳號或品牌頻道。")

        channel = channels[0]
        title = channel["snippet"]["title"]
        channel_id = channel["id"]
        print(f"\n偵測到頻道：{title}")
        print(f"頻道 ID：{channel_id}")
        answer = input("這是『半盞江湖 Half Cup of Jianghu』嗎？輸入 YES 確認：").strip()
        if answer != "YES":
            print("已取消。請重新執行並在 Google 畫面選擇正確品牌頻道。")
            return 2
        if not credentials.refresh_token:
            raise RuntimeError("Google 沒有回傳 refresh token。請撤銷舊授權後再執行一次。")

        print("\n授權成功。請將以下值加入 GitHub Actions Secret，不要貼到聊天或提交到 Git：")
        print(f"YOUTUBE_CHANNEL_ID={channel_id}")
        print(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}")
        return 0
    except HttpError as exc:
        reason = getattr(exc, "reason", str(exc))
        print(f"Google API 呼叫失敗：{reason}\n請確認 YouTube Data API v3 與 YouTube Analytics API 已啟用。", file=sys.stderr)
    except (ValueError, RuntimeError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
    except Exception as exc:  # OAuth library/browser failures vary by platform.
        print(f"OAuth 授權失敗：{exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

