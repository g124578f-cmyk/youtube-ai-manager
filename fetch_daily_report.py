"""抓取半盞江湖前一日 YouTube 私人數據並產生 Markdown/CSV。"""

from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CHANNEL_NAME = "半盞江湖 Half Cup of Jianghu"


@dataclass
class DailyStats:
    report_date: str
    views: int = 0
    estimated_minutes_watched: float = 0
    average_view_duration: float = 0
    subscribers_gained: int = 0
    subscribers_lost: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    current_subscribers: int = 0
    lifetime_views: int = 0
    video_count: int = 0


def previous_day(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("Asia/Taipei"))
    else:
        now = now.astimezone(ZoneInfo("Asia/Taipei"))
    return now.date() - timedelta(days=1)


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"缺少必要環境變數：{name}")
    return value


def credentials_from_env() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=env("GOOGLE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env("GOOGLE_CLIENT_ID"),
        client_secret=env("GOOGLE_CLIENT_SECRET"),
        scopes=SCOPES,
    )


def metric_row(response: dict, defaults: list[float]) -> list[float]:
    rows = response.get("rows", [])
    return rows[0] if rows else defaults


def fetch_data(target: date) -> tuple[DailyStats, list[dict]]:
    credentials = credentials_from_env()
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)

    channel_response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    items = channel_response.get("items", [])
    if not items:
        raise RuntimeError("登入身分沒有可讀取的 YouTube 頻道，refresh token 可能屬於錯誤帳號。")
    channel = items[0]
    expected_id = env("YOUTUBE_CHANNEL_ID")
    if channel["id"] != expected_id:
        raise RuntimeError(
            f"選錯品牌頻道：目前為 {channel['snippet']['title']} ({channel['id']})，"
            f"但 Secret 設定為 {expected_id}。請重新執行 authorize.py。"
        )

    day = target.isoformat()
    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,subscribersGained,"
        "subscribersLost,likes,comments,shares"
    )
    daily_response = analytics.reports().query(
        ids="channel==MINE", startDate=day, endDate=day, metrics=metrics
    ).execute()
    values = metric_row(daily_response, [0] * 8)
    statistics = channel["statistics"]
    stats = DailyStats(
        report_date=day,
        views=int(values[0]),
        estimated_minutes_watched=float(values[1]),
        average_view_duration=float(values[2]),
        subscribers_gained=int(values[3]),
        subscribers_lost=int(values[4]),
        likes=int(values[5]),
        comments=int(values[6]),
        shares=int(values[7]),
        current_subscribers=int(statistics.get("subscriberCount", 0)),
        lifetime_views=int(statistics.get("viewCount", 0)),
        video_count=int(statistics.get("videoCount", 0)),
    )

    top_response = analytics.reports().query(
        ids="channel==MINE", startDate=day, endDate=day,
        metrics="views", dimensions="video", sort="-views", maxResults=5,
    ).execute()
    top_rows = top_response.get("rows", [])
    ids = [row[0] for row in top_rows]
    titles: dict[str, str] = {}
    if ids:
        video_response = youtube.videos().list(part="snippet", id=",".join(ids)).execute()
        titles = {item["id"]: item["snippet"]["title"] for item in video_response.get("items", [])}
    top_videos = [
        {"id": video_id, "title": titles.get(video_id, "（影片已刪除或無法讀取）"), "views": int(views)}
        for video_id, views in top_rows
    ]
    return stats, top_videos


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def render_markdown(stats: DailyStats, top_videos: list[dict]) -> str:
    top_lines = [
        f"| {index} | [{video['title']}](https://youtu.be/{video['id']}) | {video['views']:,} |"
        for index, video in enumerate(top_videos, 1)
    ]
    if not top_lines:
        top_lines = ["| — | 當日無影片觀看資料 | 0 |"]
    return f"""# {CHANNEL_NAME}｜YouTube 每日報表

**報表日期：{stats.report_date}（台灣時間）**

## 前一天表現

| 指標 | 數值 |
|---|---:|
| 觀看次數 | {stats.views:,} |
| 觀看分鐘 | {stats.estimated_minutes_watched:,.2f} |
| 平均觀看時間 | {format_duration(stats.average_view_duration)} |
| 新增訂閱 | {stats.subscribers_gained:,} |
| 取消訂閱 | {stats.subscribers_lost:,} |
| 淨訂閱變化 | {stats.subscribers_gained - stats.subscribers_lost:+,} |
| 喜歡 | {stats.likes:,} |
| 留言 | {stats.comments:,} |
| 分享 | {stats.shares:,} |

## 頻道目前總覽

| 指標 | 數值 |
|---|---:|
| 訂閱總數 | {stats.current_subscribers:,} |
| 累積觀看總數 | {stats.lifetime_views:,} |
| 影片總數 | {stats.video_count:,} |

## 前一天觀看最高的 5 支影片

| 排名 | 影片 | 觀看次數 |
|---:|---|---:|
{chr(10).join(top_lines)}

> YouTube Analytics 的資料可能延遲或後續修正；本報表為 API 執行當下取得的數值。
"""


def upsert_history(path: Path, stats: DailyStats) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [field.name for field in fields(DailyStats)]
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    row = {name: getattr(stats, name) for name in fieldnames}
    filtered = [item for item in existing if item.get("report_date") != stats.report_date]
    filtered.append(row)
    filtered.sort(key=lambda item: str(item["report_date"]))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filtered)


def main() -> int:
    try:
        target = previous_day()
        stats, top_videos = fetch_data(target)
        report_path = Path("reports") / f"{target.isoformat()}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_markdown(stats, top_videos), encoding="utf-8")
        upsert_history(Path("data/history.csv"), stats)
        print(f"完成：{report_path} 與 data/history.csv")
        if stats.views == 0:
            print("提醒：當日 API 回傳 0 次觀看，可能確實無資料或 Analytics 尚未完成處理。")
        return 0
    except HttpError as exc:
        status = getattr(exc.resp, "status", "未知")
        reason = getattr(exc, "reason", str(exc))
        print(f"Google API 錯誤 ({status})：{reason}", file=sys.stderr)
        if status in (401, 403):
            print("請確認 refresh token 有效、API 已啟用，且 OAuth 測試使用者設定正確。", file=sys.stderr)
    except ValueError as exc:
        print(f"設定錯誤：{exc}", file=sys.stderr)
    except RuntimeError as exc:
        print(f"頻道驗證失敗：{exc}", file=sys.stderr)
    except Exception as exc:
        print(f"產生報表失敗：{exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

