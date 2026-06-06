#!/usr/bin/env python3
"""
🍅 Pomodoro Stats Helper — Emily 专用
读取 iCloud Obsidian 中的番茄钟数据，提供工时统计
"""

import json
import datetime
from pathlib import Path
from collections import defaultdict

ICLOUD_OBSIDIAN = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Auty"
DATA_DIR = ICLOUD_OBSIDIAN / "番茄钟"


def get_today_stats():
    """今日工时统计"""
    date_str = datetime.date.today().isoformat()
    return get_day_stats(date_str)


def get_day_stats(date_str):
    """某天工时统计"""
    json_path = DATA_DIR / f"{date_str}.json"
    if not json_path.exists():
        return None
    
    with open(json_path) as f:
        data = json.load(f)
    
    return {
        "date": data["date"],
        "total_hours": round(data["total_work_minutes"] / 60, 2),
        "total_minutes": data["total_work_minutes"],
        "pomodoros": data["total_pomodoros"],
        "sessions": data["sessions"],
    }


def get_week_stats():
    """本周工时统计（周一到今天）"""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    
    week_data = []
    total_minutes = 0
    total_pomodoros = 0
    days_with_work = 0
    
    for i in range(7):
        day = monday + datetime.timedelta(days=i)
        if day > today:
            break
        day_stats = get_day_stats(day.isoformat())
        if day_stats:
            week_data.append(day_stats)
            total_minutes += day_stats["total_minutes"]
            total_pomodoros += day_stats["pomodoros"]
            days_with_work += 1
    
    return {
        "start_date": monday.isoformat(),
        "end_date": today.isoformat(),
        "days_with_work": days_with_work,
        "total_hours": round(total_minutes / 60, 2),
        "total_minutes": total_minutes,
        "total_pomodoros": total_pomodoros,
        "daily": week_data,
    }


def get_month_stats(year=None, month=None):
    """月度工时统计"""
    today = datetime.date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    
    total_minutes = 0
    total_pomodoros = 0
    days_with_work = 0
    daily_data = []
    
    # 遍历当月每一天
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_stats = get_day_stats(date_str)
        if day_stats:
            daily_data.append(day_stats)
            total_minutes += day_stats["total_minutes"]
            total_pomodoros += day_stats["pomodoros"]
            days_with_work += 1
    
    return {
        "year": year,
        "month": month,
        "days_with_work": days_with_work,
        "total_hours": round(total_minutes / 60, 2),
        "total_minutes": total_minutes,
        "total_pomodoros": total_pomodoros,
        "daily": daily_data,
    }


def get_recent_days(days=7):
    """最近N天工时"""
    today = datetime.date.today()
    result = []
    
    for i in range(days):
        day = today - datetime.timedelta(days=i)
        stats = get_day_stats(day.isoformat())
        result.append({
            "date": day.isoformat(),
            "weekday": ["一", "二", "三", "四", "五", "六", "日"][day.weekday()],
            "hours": stats["total_hours"] if stats else 0,
            "pomodoros": stats["pomodoros"] if stats else 0,
            "has_data": stats is not None,
        })
    
    return list(reversed(result))


def format_summary(data, period="today"):
    """格式化摘要文本"""
    if data is None:
        return "📭 暂无数据"
    
    lines = []
    
    if period == "today":
        if "date" in data:
            lines.append(f"📅 {data['date']}")
        lines.append(f"⏱ 工作时长：{data['total_hours']:.1f} 小时（{data['total_minutes']} 分钟）")
        lines.append(f"🍅 番茄钟：{data['pomodoros']} 个")
        if data.get("sessions"):
            lines.append("")
            lines.append("📋 今日记录：")
            for s in data["sessions"]:
                icon = "✅" if s.get("completed") else "⏹"
                task = f" — {s['task']}" if s.get("task") else ""
                lines.append(f"  {icon} {s['start']}-{s['end']} ({s['duration_minutes']}分钟){task}")
    
    elif period == "week":
        lines.append(f"📅 {data['start_date']} ~ {data['end_date']}")
        lines.append(f"⏱ 总工作时长：{data['total_hours']:.1f} 小时")
        lines.append(f"🍅 总番茄钟：{data['total_pomodoros']} 个")
        lines.append(f"📆 工作天数：{data['days_with_work']} 天")
        if data.get("daily"):
            lines.append("")
            for d in data["daily"]:
                date_obj = datetime.date.fromisoformat(d["date"])
                weekday = ["一", "二", "三", "四", "五", "六", "日"][date_obj.weekday()]
                lines.append(f"  📅 {d['date']} 周{weekday}：{d['total_hours']:.1f}h | {d['pomodoros']}🍅")
    
    elif period == "month":
        lines.append(f"📅 {data['year']}年{data['month']}月")
        lines.append(f"⏱ 总工作时长：{data['total_hours']:.1f} 小时")
        lines.append(f"🍅 总番茄钟：{data['total_pomodoros']} 个")
        lines.append(f"📆 工作天数：{data['days_with_work']} 天")
        if data["days_with_work"] > 0:
            avg_hours = data["total_hours"] / data["days_with_work"]
            lines.append(f"📊 日均工作：{avg_hours:.1f} 小时")
    
    return "\n".join(lines)


# ─── 命令行入口 ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法：python3 stats.py [today|week|month|recent]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "today":
        data = get_today_stats()
        print(format_summary(data, "today"))
    
    elif cmd == "week":
        data = get_week_stats()
        print(format_summary(data, "week"))
    
    elif cmd == "month":
        data = get_month_stats()
        print(format_summary(data, "month"))
    
    elif cmd == "recent":
        data = get_recent_days(7)
        print("📊 最近7天工时：")
        for d in data:
            bar = "█" * int(d["hours"]) if d["hours"] > 0 else "-"
            print(f"  {d['date']} 周{d['weekday']}：{d['hours']:.1f}h | {d['pomodoros']}🍅 {bar}")
    
    else:
        print(f"未知命令：{cmd}")
        print("用法：python3 stats.py [today|week|month|recent]")
