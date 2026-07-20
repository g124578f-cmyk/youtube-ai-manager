import csv
from datetime import datetime, timezone

from fetch_daily_report import (
    DailyStats,
    backfill_dates,
    merge_stats,
    previous_day,
    render_markdown,
    upsert_history,
)


def sample_stats(day: str = "2026-07-12", views: int = 123) -> DailyStats:
    return DailyStats(
        report_date=day, views=views, estimated_minutes_watched=456.5,
        average_view_duration=91, subscribers_gained=5, subscribers_lost=2,
        likes=10, comments=3, shares=1, current_subscribers=999,
        lifetime_views=123456, video_count=88,
        analytics_complete=True,
    )


def test_previous_day_uses_taipei_timezone():
    # UTC 7/13 16:30 已是台灣 7/14 00:30，因此前一天應是 7/13。
    now = datetime(2026, 7, 13, 16, 30, tzinfo=timezone.utc)
    assert previous_day(now).isoformat() == "2026-07-13"


def test_backfill_dates_includes_latest_and_seven_days():
    days = backfill_dates(previous_day(datetime(2026, 7, 20, 1, tzinfo=timezone.utc)))
    assert len(days) == 7
    assert days[0].isoformat() == "2026-07-13"
    assert days[-1].isoformat() == "2026-07-19"


def test_csv_does_not_duplicate_same_date(tmp_path):
    path = tmp_path / "data" / "history.csv"
    upsert_history(path, sample_stats(views=100))
    upsert_history(path, sample_stats(views=200))
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["views"] == "200"


def test_markdown_format_contains_sections_and_top_video():
    report = render_markdown(
        sample_stats(), [{"id": "abc123", "title": "測試影片", "views": 77}]
    )
    assert "# 半盞江湖 Half Cup of Jianghu｜YouTube 每日報表" in report
    assert "報表日期：2026-07-12" in report
    assert "| 觀看次數 | 123 |" in report
    assert "| 平均觀看時間 | 01:31 |" in report
    assert "[測試影片](https://youtu.be/abc123)" in report
    assert "Analytics 已回傳" in report


def test_pending_response_does_not_replace_existing_metrics():
    existing = sample_stats(views=321)
    fetched = DailyStats(
        report_date=existing.report_date,
        current_subscribers=1005,
        lifetime_views=124000,
        video_count=90,
        analytics_complete=False,
    )
    merged = merge_stats(existing, fetched, update_snapshot=True)
    assert merged.views == 321
    assert merged.analytics_complete is True
    assert merged.current_subscribers == 1005


def test_old_backfill_preserves_historical_snapshot():
    existing = sample_stats()
    fetched = sample_stats(views=456)
    fetched.current_subscribers = 2000
    fetched.lifetime_views = 999999
    fetched.video_count = 100
    merged = merge_stats(existing, fetched, update_snapshot=False)
    assert merged.views == 456
    assert merged.current_subscribers == 999
    assert merged.lifetime_views == 123456
    assert merged.video_count == 88
