#!/usr/bin/env python3
"""
Pomodoro for macOS

A native Cocoa window for the existing Pomodoro data model. It keeps the
iCloud/Obsidian work log format used by stats.py while offering a regular
double-clickable macOS app experience.
"""

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import objc
from objc import python_method
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSProgressIndicator,
    NSSound,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSTimer


ICLOUD_OBSIDIAN = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Auty"
DATA_DIR = ICLOUD_OBSIDIAN / "番茄钟"
SUPPORT_DIR = Path.home() / "Library/Application Support/Pomodoro"
CONFIG_PATH = SUPPORT_DIR / "config.json"
STATE_PATH = SUPPORT_DIR / "state.json"

DEFAULT_CONFIG = {
    "work_duration": 25,
    "short_break": 5,
    "long_break": 15,
    "long_break_interval": 4,
    "auto_start_break": True,
    "auto_start_work": False,
    "sound_enabled": True,
}


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(config)
        return merged
    return dict(DEFAULT_CONFIG)


def save_config(config):
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def read_today_totals():
    date_str = dt.date.today().isoformat()
    path = DATA_DIR / f"{date_str}.json"
    if not path.exists():
        return 0, 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return int(data.get("total_pomodoros", 0)), int(data.get("total_work_minutes", 0) * 60)


def format_time(seconds):
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def notify(title, message, sound=True):
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    if sound:
        try:
            NSSound.soundNamed_("Glass").play()
        except Exception:
            pass


def log_session(start_time, end_time, duration_seconds, task, completed):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    date_str = start_time.strftime("%Y-%m-%d")
    json_path = DATA_DIR / f"{date_str}.json"
    md_path = DATA_DIR / f"{date_str}.md"

    session = {
        "start": start_time.strftime("%H:%M:%S"),
        "end": end_time.strftime("%H:%M:%S"),
        "duration_minutes": round(duration_seconds / 60, 1),
        "task": task or "",
        "completed": completed,
    }

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "date": date_str,
            "sessions": [],
            "total_work_minutes": 0,
            "total_pomodoros": 0,
        }

    data["sessions"].append(session)
    data["total_work_minutes"] = round(sum(s["duration_minutes"] for s in data["sessions"]), 1)
    data["total_pomodoros"] = sum(1 for s in data["sessions"] if s["completed"])

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    update_markdown(data, md_path)


def update_markdown(data, md_path):
    total_min = data["total_work_minutes"]
    lines = [
        f"# {data['date']} 番茄钟日报",
        "",
        f"**总工作时长：** {total_min / 60:.1f} 小时（{total_min:.0f} 分钟）",
        f"**完成番茄钟：** {data['total_pomodoros']} 个",
        f"**记录条数：** {len(data['sessions'])} 条",
        "",
        "---",
        "",
        "## 工作记录",
        "",
        "| # | 开始 | 结束 | 时长 | 任务 | 状态 |",
        "|---|------|------|------|------|------|",
    ]
    for index, session in enumerate(data["sessions"], 1):
        status = "完成" if session["completed"] else "中断"
        task = session["task"] if session["task"] else "-"
        lines.append(
            f"| {index} | {session['start']} | {session['end']} | "
            f"{session['duration_minutes']}分钟 | {task} | {status} |"
        )
    lines.extend(["", "---", "", f"*最后更新：{dt.datetime.now().strftime('%H:%M:%S')}*"])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class PomodoroWindow(NSObject):
    window = objc.ivar()
    timer = objc.ivar()

    def init(self):
        self = objc.super(PomodoroWindow, self).init()
        if self is None:
            return None

        self.config = load_config()
        self.state = "idle"
        self.current_type = None
        self.current_task = ""
        self.remaining_seconds = 0
        self.session_start = None
        self.today_pomodoros, self.total_work_seconds = read_today_totals()
        self.timer = None
        return self

    def applicationDidFinishLaunching_(self, notification):
        self.build_window()
        self.restore_state()
        NSApp.activateIgnoringOtherApps_(True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        return True

    @python_method
    def build_window(self):
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 460, 600),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Pomodoro")
        self.window.center()
        self.window.setMinSize_((420, 560))

        content = self.window.contentView()
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())

        self.title_label = self.label("Pomodoro", 28, 540, 404, 32, 16, bold=True)
        self.status_label = self.label("准备开始", 28, 510, 404, 26, 13)
        self.time_label = self.label("25:00", 28, 410, 404, 84, 64, bold=True, center=True)
        self.progress = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(64, 388, 332, 10))
        self.progress.setIndeterminate_(False)
        self.progress.setMinValue_(0)
        self.progress.setMaxValue_(1)
        self.progress.setDoubleValue_(0)
        content.addSubview_(self.progress)

        self.task_label = self.label("任务", 28, 348, 404, 22, 12)
        self.task_field = NSTextField.alloc().initWithFrame_(NSMakeRect(28, 316, 404, 30))
        self.task_field.setPlaceholderString_("这一个番茄钟要推进什么？")
        content.addSubview_(self.task_field)

        self.work_button = self.button("开始工作", 28, 260, 128, 36, "startWork:")
        self.short_button = self.button("短休息", 166, 260, 128, 36, "startShortBreak:")
        self.long_button = self.button("长休息", 304, 260, 128, 36, "startLongBreak:")
        self.pause_button = self.button("暂停", 28, 210, 197, 36, "togglePause:")
        self.stop_button = self.button("结束当前", 235, 210, 197, 36, "stopSession:")

        self.stats_label = self.label("", 28, 154, 404, 40, 13)
        self.auto_break = self.checkbox("工作结束自动开始休息", 28, 112, self.config["auto_start_break"], "toggleAutoBreak:")
        self.auto_work = self.checkbox("休息结束自动开始工作", 28, 84, self.config["auto_start_work"], "toggleAutoWork:")
        self.sound_enabled = self.checkbox("完成时播放提示音", 28, 56, self.config["sound_enabled"], "toggleSound:")

        self.prefs_button = self.button("偏好设置", 28, 18, 128, 28, "openPreferences:")
        self.open_data_button = self.button("打开数据文件夹", 166, 18, 148, 28, "openDataFolder:")

        self.update_ui()
        self.window.makeKeyAndOrderFront_(None)

    @python_method
    def label(self, text, x, y, width, height, size, bold=False, center=False):
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
        if center:
            label.setAlignment_(2)
        self.window.contentView().addSubview_(label)
        return label

    @python_method
    def button(self, title, x, y, width, height, action):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        button.setTitle_(title)
        button.setBezelStyle_(NSBezelStyleRounded)
        button.setTarget_(self)
        button.setAction_(action)
        self.window.contentView().addSubview_(button)
        return button

    @python_method
    def checkbox(self, title, x, y, checked, action):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, 280, 22))
        button.setButtonType_(3)
        button.setTitle_(title)
        button.setState_(1 if checked else 0)
        button.setTarget_(self)
        button.setAction_(action)
        self.window.contentView().addSubview_(button)
        return button

    @python_method
    def duration_seconds(self):
        if self.current_type == "work":
            return self.config["work_duration"] * 60
        if self.current_type == "short_break":
            return self.config["short_break"] * 60
        if self.current_type == "long_break":
            return self.config["long_break"] * 60
        return self.config["work_duration"] * 60

    @python_method
    def start_timer(self):
        if self.timer is not None:
            self.timer.invalidate()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "tick:", None, True
        )

    @python_method
    def stop_timer(self):
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None

    def startWork_(self, sender):
        self.start_session("work")

    def startShortBreak_(self, sender):
        self.start_session("short_break")

    def startLongBreak_(self, sender):
        self.start_session("long_break")

    @python_method
    def start_session(self, session_type):
        self.current_task = str(self.task_field.stringValue()).strip()
        self.current_type = session_type
        self.state = "working" if session_type == "work" else "breaking"
        self.remaining_seconds = self.duration_seconds()
        self.session_start = dt.datetime.now()
        self.start_timer()
        self.save_state()
        self.update_ui()

        if session_type == "work":
            notify("开始工作", f"专注 {self.config['work_duration']} 分钟", False)
        elif session_type == "short_break":
            notify("短休息", f"{self.config['short_break']} 分钟", False)
        else:
            notify("长休息", f"{self.config['long_break']} 分钟", False)

    def togglePause_(self, sender):
        if self.state == "paused":
            self.state = "working" if self.current_type == "work" else "breaking"
            self.start_timer()
        elif self.state in ("working", "breaking"):
            self.state = "paused"
            self.stop_timer()
        self.save_state()
        self.update_ui()

    def stopSession_(self, sender):
        was_work = self.current_type == "work"
        if was_work and self.session_start:
            actual = self.duration_seconds() - self.remaining_seconds
            if actual > 30:
                log_session(self.session_start, dt.datetime.now(), int(actual), self.current_task, False)

        self.stop_timer()
        self.clear_state()
        if was_work:
            notify("番茄钟已结束", "已记录这段专注时间", self.config["sound_enabled"])

    def tick_(self, sender):
        if self.state == "paused":
            return
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            if self.remaining_seconds % 60 == 0:
                self.save_state()
            self.update_ui()
            return
        self.session_end()

    @python_method
    def session_end(self):
        self.stop_timer()
        end_time = dt.datetime.now()

        if self.current_type == "work":
            duration = self.duration_seconds()
            log_session(self.session_start, end_time, duration, self.current_task, True)
            self.today_pomodoros += 1
            self.total_work_seconds += duration
            notify("番茄钟完成", "可以休息一下了", self.config["sound_enabled"])
            if self.config["auto_start_break"]:
                next_type = (
                    "long_break"
                    if self.today_pomodoros % self.config["long_break_interval"] == 0
                    else "short_break"
                )
                self.start_session(next_type)
                return
        elif self.current_type in ("short_break", "long_break"):
            notify("休息结束", "准备开始下一个番茄钟", self.config["sound_enabled"])
            if self.config["auto_start_work"]:
                self.start_session("work")
                return

        self.clear_state()

    @python_method
    def clear_state(self):
        self.state = "idle"
        self.current_type = None
        self.current_task = ""
        self.remaining_seconds = 0
        self.session_start = None
        self.task_field.setStringValue_("")
        STATE_PATH.unlink(missing_ok=True)
        self.update_ui()

    @python_method
    def save_state(self):
        SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "state": self.state,
            "current_type": self.current_type,
            "current_task": self.current_task,
            "remaining_seconds": self.remaining_seconds,
            "session_start": self.session_start.isoformat() if self.session_start else None,
            "saved_at": dt.datetime.now().isoformat(),
        }
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    @python_method
    def restore_state(self):
        if not STATE_PATH.exists():
            return
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            saved_at = dt.datetime.fromisoformat(payload["saved_at"])
            if (dt.datetime.now() - saved_at).total_seconds() > 3600:
                STATE_PATH.unlink(missing_ok=True)
                return

            self.state = payload["state"]
            self.current_type = payload["current_type"]
            self.current_task = payload.get("current_task", "")
            self.remaining_seconds = int(payload.get("remaining_seconds", 0))
            start = payload.get("session_start")
            self.session_start = dt.datetime.fromisoformat(start) if start else None
            self.task_field.setStringValue_(self.current_task)
            if self.state in ("working", "breaking"):
                self.start_timer()
            self.update_ui()
        except Exception:
            STATE_PATH.unlink(missing_ok=True)

    @python_method
    def update_ui(self):
        total = self.duration_seconds()
        remaining = self.remaining_seconds if self.state != "idle" else total
        progress = 0 if total <= 0 else 1 - (remaining / total)
        self.time_label.setStringValue_(format_time(remaining))
        self.progress.setDoubleValue_(progress)

        if self.state == "idle":
            status = "准备开始"
        elif self.state == "paused":
            status = "已暂停"
        elif self.current_type == "work":
            status = "工作中" + (f" - {self.current_task}" if self.current_task else "")
        elif self.current_type == "short_break":
            status = "短休息中"
        else:
            status = "长休息中"
        self.status_label.setStringValue_(status)

        hours = self.total_work_seconds / 3600
        self.stats_label.setStringValue_(f"今日：{hours:.1f} 小时 | {self.today_pomodoros} 个番茄钟")

        active = self.state in ("working", "breaking")
        paused = self.state == "paused"
        self.work_button.setEnabled_(not active and not paused)
        self.short_button.setEnabled_(not active and not paused)
        self.long_button.setEnabled_(not active and not paused)
        self.pause_button.setEnabled_(active or paused)
        self.stop_button.setEnabled_(active or paused)
        self.pause_button.setTitle_("继续" if paused else "暂停")

    def toggleAutoBreak_(self, sender):
        self.config["auto_start_break"] = bool(sender.state())
        save_config(self.config)

    def toggleAutoWork_(self, sender):
        self.config["auto_start_work"] = bool(sender.state())
        save_config(self.config)

    def toggleSound_(self, sender):
        self.config["sound_enabled"] = bool(sender.state())
        save_config(self.config)

    def openDataFolder_(self, sender):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(DATA_DIR)], check=False)

    def openPreferences_(self, sender):
        from AppKit import NSAlert, NSAlertFirstButtonReturn

        alert = NSAlert.alloc().init()
        alert.setMessageText_("偏好设置")
        alert.setInformativeText_(
            "每行一个数字：工作分钟、短休息分钟、长休息分钟、长休息间隔。"
        )
        alert.addButtonWithTitle_("保存")
        alert.addButtonWithTitle_("取消")

        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 260, 88))
        field.setStringValue_(
            f"{self.config['work_duration']}\n"
            f"{self.config['short_break']}\n"
            f"{self.config['long_break']}\n"
            f"{self.config['long_break_interval']}"
        )
        alert.setAccessoryView_(field)
        if alert.runModal() == NSAlertFirstButtonReturn:
            try:
                values = [int(line.strip()) for line in str(field.stringValue()).splitlines() if line.strip()]
                if len(values) >= 4:
                    self.config["work_duration"] = max(1, min(120, values[0]))
                    self.config["short_break"] = max(1, min(30, values[1]))
                    self.config["long_break"] = max(1, min(60, values[2]))
                    self.config["long_break_interval"] = max(1, min(12, values[3]))
                    save_config(self.config)
                    self.update_ui()
            except ValueError:
                notify("设置格式错误", "请输入数字", self.config["sound_enabled"])


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = PomodoroWindow.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
