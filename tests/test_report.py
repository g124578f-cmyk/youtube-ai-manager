import csv
from datetime import datetime, timezone

from fetch_daily_report import DailyStats, previous_day, render_markdown, upsert_history


def sample_stats(day: str = "2026-07-12", views: int = 123) -> DailyStats:
    return DailyStats(
        report_date=day, views=views, estimated_minutes_watched=456.5,
        average_view_duration=91, subscribers_gained=5, subscribers_lost=2,
        likes=10, comments=3, shares=1, current_subscribers=999,
        lifetime_views=123456, video_count=88,
    )


def test_previous_day_uses_taipei_timezone():
    # UTC 7/13 16:30 已是台灣 7/14 00:30，因此前一天應是 7/13。
    now = datetime(2026, 7, 13, 16, 30, tzinfo=timezone.utc)
    assert previous_day(now).isoformat() == "2026-07-13"


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

