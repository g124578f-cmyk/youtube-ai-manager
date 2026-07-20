"""抓取半盞江湖 YouTube 私人數據，並回補最近數日的 Markdown/CSV。"""

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
BACKFILL_DAYS = 7
DAILY_METRIC_FIELDS = (
    "views",
    "estimated_minutes_watched",
    "average_view_duration",
    "subscribers_gained",
    "subscribers_lost",
    "likes",
    "comments",
    "shares",
)


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
    analytics_complete: bool = False


def previous_day(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("Asia/Taipei"))
    else:
        now = now.astimezone(ZoneInfo("Asia/Taipei"))
    return now.date() - timedelta(days=1)


def backfill_dates(end: date, days: int = BACKFILL_DAYS) -> list[date]:
    """回傳由舊到新的回補日期，結尾為 end。"""
    if days < 1:
        raise ValueError("回補天數至少必須為 1")
    return [end - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


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


def build_clients() -> tuple[object, object, dict]:
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
    return youtube, analytics, channel


def fetch_data(
    target: date,
    youtube: object | None = None,
    analytics: object | None = None,
    channel: dict | None = None,
) -> tuple[DailyStats, list[dict]]:
    if youtube is None or analytics is None or channel is None:
        youtube, analytics, channel = build_clients()

    day = target.isoformat()
    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,subscribersGained,"
        "subscribersLost,likes,comments,shares"
    )
    daily_response = analytics.reports().query(
        ids="channel==MINE", startDate=day, endDate=day, metrics=metrics
    ).execute()
    rows = daily_response.get("rows", [])
    analytics_complete = bool(rows)
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
        analytics_complete=analytics_complete,
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
        message = "當日無影片觀看資料" if stats.analytics_complete else "資料處理中，稍後自動補抓"
        top_lines = [f"| — | {message} | — |"]
    status_note = (
        "> ✅ YouTube Analytics 已回傳此日明細；數值仍可能由 YouTube 後續修正。"
        if stats.analytics_complete
        else "> ⚠️ YouTube Analytics 尚未完成此日資料；畫面中的 0 不代表沒有流量，系統會在未來 7 天自動補抓。"
    )
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

{status_note}
"""


def read_history(path: Path) -> dict[str, DailyStats]:
    if not path.exists():
        return {}
    result: dict[str, DailyStats] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            day = row.get("report_date", "")
            if not day:
                continue
            result[day] = DailyStats(
                report_date=day,
                views=int(float(row.get("views") or 0)),
                estimated_minutes_watched=float(row.get("estimated_minutes_watched") or 0),
                average_view_duration=float(row.get("average_view_duration") or 0),
                subscribers_gained=int(float(row.get("subscribers_gained") or 0)),
                subscribers_lost=int(float(row.get("subscribers_lost") or 0)),
                likes=int(float(row.get("likes") or 0)),
                comments=int(float(row.get("comments") or 0)),
                shares=int(float(row.get("shares") or 0)),
                current_subscribers=int(float(row.get("current_subscribers") or 0)),
                lifetime_views=int(float(row.get("lifetime_views") or 0)),
                video_count=int(float(row.get("video_count") or 0)),
                analytics_complete=str(row.get("analytics_complete", "")).lower() == "true",
            )
    return result


def merge_stats(
    existing: DailyStats | None,
    fetched: DailyStats,
    update_snapshot: bool,
) -> DailyStats:
    """合併回補結果；空回應不能覆蓋既有明細，舊日期保留當時總量快照。"""
    if existing and not fetched.analytics_complete:
        for name in DAILY_METRIC_FIELDS:
            setattr(fetched, name, getattr(existing, name))
        fetched.analytics_complete = existing.analytics_complete
    if existing and not update_snapshot:
        fetched.current_subscribers = existing.current_subscribers
        fetched.lifetime_views = existing.lifetime_views
        fetched.video_count = existing.video_count
    return fetched


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
        latest = previous_day()
        history_path = Path("data/history.csv")
        history = read_history(history_path)
        youtube, analytics, channel = build_clients()
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)

        for target in backfill_dates(latest):
            day = target.isoformat()
            existing = history.get(day)
            fetched, top_videos = fetch_data(target, youtube, analytics, channel)
            api_complete = fetched.analytics_complete
            stats = merge_stats(existing, fetched, update_snapshot=target == latest)
            report_path = reports_dir / f"{day}.md"

            # API 有明細時重建報表；昨日尚未完成時仍更新最新總量快照。
            # 舊日若曾有完整報表，空回應不會將它覆蓋成 0。
            if api_complete or target == latest or not report_path.exists():
                report_path.write_text(render_markdown(stats, top_videos), encoding="utf-8")
            upsert_history(history_path, stats)
            history[day] = stats
            state = "已完成" if stats.analytics_complete else "處理中"
            print(f"{day}：Analytics {state}")

        print(f"完成：回補最近 {BACKFILL_DAYS} 天報表與 data/history.csv")
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
