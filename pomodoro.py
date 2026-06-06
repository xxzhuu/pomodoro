#!/usr/bin/env python3
"""
🍅 Pomodoro Timer — macOS 菜单栏番茄钟
工作数据实时同步到 iCloud Obsidian 仓库（Auty/番茄钟/）
Emily 可随时读取数据帮你统计每日工时
"""

import os
import json
import threading
import datetime
from pathlib import Path

import rumps
import objc
from Foundation import NSDate

# ─── 路径配置 ───────────────────────────────────────────
ICLOUD_OBSIDIAN = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Auty"
DATA_DIR = ICLOUD_OBSIDIAN / "番茄钟"
CONFIG_PATH = Path(__file__).parent / "config.json"
STATE_PATH = Path(__file__).parent / "state.json"

# ─── 默认配置 ───────────────────────────────────────────
DEFAULT_CONFIG = {
    "work_duration": 25,        # 工作时间（分钟）
    "short_break": 5,           # 短休息
    "long_break": 15,           # 长休息
    "long_break_interval": 4,   # 几个番茄钟后长休息
    "auto_start_break": True,   # 工作结束自动开始休息
    "auto_start_work": False,   # 休息结束自动开始工作
    "sound_enabled": True,
}

# ─── 番茄钟应用 ─────────────────────────────────────────
class PomodoroApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="Pomodoro",
            title="🍅",
            quit_button=None,
        )
        
        # 状态
        self.state = "idle"          # idle | working | breaking | paused
        self.remaining_seconds = 0
        self.current_type = None     # 'work' | 'short_break' | 'long_break'
        self.current_task = ""
        self.session_start = None    # datetime
        self.paused_at = None        # datetime
        self.today_pomodoros = 0     # 今天完成的工作番茄数
        self.total_work_seconds = 0  # 今天总工作秒数
        self._loading = True
        
        # 加载配置
        self.config = self._load_config()
        
        # 加载今日数据
        self._load_today_data()
        
        # 菜单项
        self.menu_items = {}
        self._build_menu()
        
        # 计时器
        self.timer = rumps.Timer(self._tick, 1)
        
        # 恢复上次状态
        self._restore_state()
        self._loading = False
        
    # ─── 配置 ───────────────────────────────────────────
    def _load_config(self):
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        return dict(DEFAULT_CONFIG)
    
    def _save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    # ─── 状态持久化 ─────────────────────────────────────
    def _save_state(self):
        state = {
            "state": self.state,
            "remaining_seconds": self.remaining_seconds,
            "current_type": self.current_type,
            "current_task": self.current_task,
            "session_start": self.session_start.isoformat() if self.session_start else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "saved_at": datetime.datetime.now().isoformat(),
        }
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    
    def _restore_state(self):
        if not STATE_PATH.exists():
            return
        try:
            with open(STATE_PATH) as f:
                state = json.load(f)
            
            saved = datetime.datetime.fromisoformat(state.get("saved_at", ""))
            if (datetime.datetime.now() - saved).total_seconds() > 3600:
                STATE_PATH.unlink(missing_ok=True)
                return
            
            if state["state"] in ("working", "breaking"):
                self.state = state["state"]
                self.current_type = state["current_type"]
                self.current_task = state.get("current_task", "")
                if state["session_start"]:
                    self.session_start = datetime.datetime.fromisoformat(state["session_start"])
                elapsed = (datetime.datetime.now() - self.session_start).total_seconds()
                total_dur = self._get_duration_seconds()
                self.remaining_seconds = max(0, total_dur - int(elapsed))
                self.timer.start()
                if self.current_type in ("short_break", "long_break"):
                    self.title = "☕"
                else:
                    self.title = "🍅"
                self._update_menu_for_state()
                self._update_title()
            elif state["state"] == "paused":
                self.state = "paused"
                self.remaining_seconds = state["remaining_seconds"]
                self.current_type = state["current_type"]
                self.current_task = state.get("current_task", "")
                if state["session_start"]:
                    self.session_start = datetime.datetime.fromisoformat(state["session_start"])
                self._update_menu_for_state()
            
            STATE_PATH.unlink(missing_ok=True)
        except Exception:
            STATE_PATH.unlink(missing_ok=True)
    
    # ─── 菜单构建 ───────────────────────────────────────
    def _build_menu(self):
        # 清除旧菜单
        self.menu.clear()
        self.menu_items.clear()
        
        # 状态显示
        self.menu_items["status"] = rumps.MenuItem("🍅 就绪", callback=None)
        self.menu.add(self.menu_items["status"])
        
        self.menu.add(rumps.separator)
        
        # 操作按钮
        self.menu_items["start_work"] = rumps.MenuItem(
            f"▶ 开始工作 ({self.config['work_duration']}分钟)",
            callback=self._start_work
        )
        self.menu.add(self.menu_items["start_work"])
        
        self.menu_items["short_break"] = rumps.MenuItem(
            f"☕ 短休息 ({self.config['short_break']}分钟)",
            callback=self._start_short_break
        )
        self.menu.add(self.menu_items["short_break"])
        
        self.menu_items["long_break"] = rumps.MenuItem(
            f"🛌 长休息 ({self.config['long_break']}分钟)",
            callback=self._start_long_break
        )
        self.menu.add(self.menu_items["long_break"])
        
        self.menu_items["pause"] = rumps.MenuItem(
            "⏸ 暂停",
            callback=self._toggle_pause
        )
        self.menu.add(self.menu_items["pause"])
        
        self.menu_items["stop"] = rumps.MenuItem(
            "⏹ 结束当前",
            callback=self._stop_session
        )
        self.menu.add(self.menu_items["stop"])
        
        self.menu.add(rumps.separator)
        
        # 任务备注
        self.menu_items["task_note"] = rumps.MenuItem(
            "📋 设置任务备注...",
            callback=self._set_task_note
        )
        self.menu.add(self.menu_items["task_note"])
        
        # 今日统计
        self.menu.add(rumps.separator)
        self.menu_items["today_stats"] = rumps.MenuItem(
            self._today_stats_text(),
            callback=None
        )
        self.menu.add(self.menu_items["today_stats"])
        
        # 打开数据文件夹
        self.menu_items["open_data"] = rumps.MenuItem(
            "📁 打开数据文件夹",
            callback=self._open_data_folder
        )
        self.menu.add(self.menu_items["open_data"])
        
        self.menu.add(rumps.separator)
        
        # 设置
        self.menu_items["preferences"] = rumps.MenuItem(
            "⚙️ 偏好设置...",
            callback=self._preferences
        )
        self.menu.add(self.menu_items["preferences"])
        
        # 退出
        self.menu_items["quit"] = rumps.MenuItem(
            "❌ 退出",
            callback=self._quit_app
        )
        self.menu.add(self.menu_items["quit"])
        
        self._update_menu_for_state()
    
    def _update_menu_for_state(self):
        """根据状态启用/禁用菜单项"""
        m = self.menu_items
        
        if self.state == "idle":
            m["start_work"].set_callback(self._start_work)
            m["short_break"].set_callback(self._start_short_break)
            m["long_break"].set_callback(self._start_long_break)
            m["pause"].title = "⏸ 暂停"
            m["pause"].set_callback(None)
            m["stop"].set_callback(None)
            
        elif self.state in ("working", "breaking"):
            m["start_work"].set_callback(None)
            m["short_break"].set_callback(None)
            m["long_break"].set_callback(None)
            m["pause"].title = "⏸ 暂停"
            m["pause"].set_callback(self._toggle_pause)
            m["stop"].set_callback(self._stop_session)
            
        elif self.state == "paused":
            m["start_work"].set_callback(None)
            m["short_break"].set_callback(None)
            m["long_break"].set_callback(None)
            m["pause"].title = "▶ 继续"
            m["pause"].set_callback(self._toggle_pause)
            m["stop"].set_callback(self._stop_session)
    
    # ─── 计时器 ─────────────────────────────────────────
    def _tick(self, _):
        if self.state == "paused":
            return
        
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self._update_title()
            
            # 每分钟保存一次状态
            if self.remaining_seconds % 60 == 0:
                self._save_state()
        else:
            self._session_end()
    
    def _update_title(self):
        """更新菜单栏标题显示倒计时"""
        mins = self.remaining_seconds // 60
        secs = self.remaining_seconds % 60
        icon = "🍅" if self.current_type == "work" else "☕"
        self.title = f"{icon} {mins}:{secs:02d}"
        
        # 也更新状态行
        if self.current_type == "work":
            status = f"🍅 工作中 — {self.current_task}" if self.current_task else "🍅 工作中"
        elif self.current_type == "short_break":
            status = "☕ 短休息中"
        elif self.current_type == "long_break":
            status = "🛌 长休息中"
        else:
            status = "🍅 就绪"
        
        if self.state == "paused":
            status = "⏸ " + status + "（已暂停）"
        
        self.menu_items["status"].title = status
    
    # ─── 时长计算 ───────────────────────────────────────
    def _get_duration_seconds(self):
        if self.current_type == "work":
            return self.config["work_duration"] * 60
        elif self.current_type == "short_break":
            return self.config["short_break"] * 60
        elif self.current_type == "long_break":
            return self.config["long_break"] * 60
        return 25 * 60
    
    # ─── 启动番茄钟 ─────────────────────────────────────
    def _start_work(self, _=None):
        self.state = "working"
        self.current_type = "work"
        self.remaining_seconds = self.config["work_duration"] * 60
        self.session_start = datetime.datetime.now()
        self.timer.start()
        self._update_menu_for_state()
        self._update_title()
        self._save_state()
        self._notify("🍅 开始工作！", f"专注 {self.config['work_duration']} 分钟" + 
                      (f" — {self.current_task}" if self.current_task else ""))
    
    def _start_short_break(self, _=None):
        self.state = "breaking"
        self.current_type = "short_break"
        self.remaining_seconds = self.config["short_break"] * 60
        self.session_start = datetime.datetime.now()
        self.timer.start()
        self._update_menu_for_state()
        self._update_title()
        self._save_state()
        self._notify("☕ 短休息", f"{self.config['short_break']} 分钟，起来活动一下")
    
    def _start_long_break(self, _=None):
        self.state = "breaking"
        self.current_type = "long_break"
        self.remaining_seconds = self.config["long_break"] * 60
        self.session_start = datetime.datetime.now()
        self.timer.start()
        self._update_menu_for_state()
        self._update_title()
        self._save_state()
        self._notify("🛌 长休息", f"{self.config['long_break']} 分钟，好好休息")
    
    def _toggle_pause(self, _=None):
        if self.state == "paused":
            # 恢复
            if self.current_type == "work":
                self.state = "working"
            else:
                self.state = "breaking"
            self.timer.start()
            self._update_menu_for_state()
            self._update_title()
            self._save_state()
            self._notify("▶ 继续", "计时器已恢复")
        elif self.state in ("working", "breaking"):
            # 暂停
            self.state = "paused"
            self.timer.stop()
            self._update_menu_for_state()
            self._update_title()
            self._save_state()
    
    def _stop_session(self, _=None):
        was_work = self.current_type == "work"
        session_start = self.session_start
        
        self.timer.stop()
        
        if was_work and session_start:
            # 把已完成的时间记录进去
            elapsed = (datetime.datetime.now() - session_start).total_seconds()
            duration_seconds = self._get_duration_seconds()
            actual_seconds = duration_seconds - self.remaining_seconds
            if actual_seconds > 30:  # 至少工作了30秒才算
                self._log_session(session_start, datetime.datetime.now(), 
                                  int(actual_seconds), self.current_task, completed=False)
        
        self.state = "idle"
        self.current_type = None
        self.current_task = ""
        self.session_start = None
        self.remaining_seconds = 0
        self.title = "🍅"
        self._update_menu_for_state()
        self._update_title()
        STATE_PATH.unlink(missing_ok=True)
        
        if was_work:
            self._notify("⏹ 番茄钟已取消", "这次不算，再来一个吧 💪")
    
    def _session_end(self):
        """计时器归零，会话结束"""
        self.timer.stop()
        end_time = datetime.datetime.now()
        
        if self.current_type == "work":
            # 记录工作番茄
            duration_seconds = self._get_duration_seconds()
            self._log_session(self.session_start, end_time, duration_seconds, 
                            self.current_task, completed=True)
            self.today_pomodoros += 1
            self.total_work_seconds += duration_seconds
            self._notify("🍅 番茄钟完成！", 
                        f"已完成 {self.today_pomodoros} 个番茄钟" +
                        (f" — {self.current_task}" if self.current_task else ""))
            self._play_sound()
            
            # 自动开始休息
            if self.config["auto_start_break"]:
                if self.today_pomodoros % self.config["long_break_interval"] == 0:
                    self._start_long_break()
                else:
                    self._start_short_break()
                return
            
        elif self.current_type in ("short_break", "long_break"):
            self._notify("⏰ 休息结束", "准备开始下一个番茄钟！")
            self._play_sound()
            
            # 自动开始工作
            if self.config["auto_start_work"]:
                self._start_work()
                return
        
        # 回到空闲
        self.state = "idle"
        self.current_type = None
        self.current_task = ""
        self.session_start = None
        self.remaining_seconds = 0
        self.title = "🍅"
        self._update_menu_for_state()
        self._update_title()
        STATE_PATH.unlink(missing_ok=True)
    
    # ─── 数据记录 ───────────────────────────────────────
    def _log_session(self, start_time, end_time, duration_seconds, task, completed):
        """记录工作会话到 iCloud Obsidian"""
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
        
        # 更新 JSON 文件
        if json_path.exists():
            with open(json_path) as f:
                data = json.load(f)
        else:
            data = {
                "date": date_str,
                "sessions": [],
                "total_work_minutes": 0,
                "total_pomodoros": 0,
            }
        
        data["sessions"].append(session)
        data["total_work_minutes"] = round(
            sum(s["duration_minutes"] for s in data["sessions"]), 1
        )
        data["total_pomodoros"] = sum(1 for s in data["sessions"] if s["completed"])
        
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # 更新 Markdown 文件
        self._update_markdown(data, md_path)
        
        # 清理状态文件
        STATE_PATH.unlink(missing_ok=True)
        
        # 更新菜单统计
        self.menu_items["today_stats"].title = self._today_stats_text()
    
    def _update_markdown(self, data, md_path):
        """生成美观的 Markdown 日报文件"""
        date_str = data["date"]
        total_min = data["total_work_minutes"]
        total_hours = total_min / 60
        pomodoros = data["total_pomodoros"]
        
        lines = [
            f"# 🍅 {date_str} 番茄钟日报",
            "",
            f"**总工作时长：** {total_hours:.1f} 小时（{total_min:.0f} 分钟）",
            f"**完成番茄钟：** {pomodoros} 个 🍅",
            f"**记录条数：** {len(data['sessions'])} 条",
            "",
            "---",
            "",
            "## 📋 工作记录",
            "",
            "| # | 开始 | 结束 | 时长 | 任务 | 状态 |",
            "|---|------|------|------|------|------|",
        ]
        
        for i, s in enumerate(data["sessions"], 1):
            status = "✅ 完成" if s["completed"] else "⏹ 中断"
            task = s["task"] if s["task"] else "-"
            lines.append(
                f"| {i} | {s['start']} | {s['end']} | {s['duration_minutes']}分钟 | {task} | {status} |"
            )
        
        lines.extend([
            "",
            "---",
            "",
            f"*最后更新：{datetime.datetime.now().strftime('%H:%M:%S')}*",
        ])
        
        with open(md_path, "w") as f:
            f.write("\n".join(lines) + "\n")
    
    def _load_today_data(self):
        """加载今日数据"""
        date_str = datetime.date.today().isoformat()
        json_path = DATA_DIR / f"{date_str}.json"
        
        if json_path.exists():
            with open(json_path) as f:
                data = json.load(f)
            self.today_pomodoros = data.get("total_pomodoros", 0)
            self.total_work_seconds = int(data.get("total_work_minutes", 0) * 60)
    
    # ─── 通知 ───────────────────────────────────────────
    def _notify(self, title, subtitle=""):
        """发送系统通知"""
        try:
            rumps.notification(
                title=title,
                subtitle=subtitle,
                message="",
                sound=self.config.get("sound_enabled", True),
            )
        except Exception:
            pass  # 通知发送失败不影响主要功能
    
    def _play_sound(self):
        """播放提示音"""
        if not self.config.get("sound_enabled", True):
            return
        try:
            # 使用系统提示音
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
        except Exception:
            pass
    
    # ─── 任务备注 ───────────────────────────────────────
    def _set_task_note(self, _=None):
        """设置当前/下次工作番茄的任务备注"""
        response = rumps.Window(
            message="当前任务是什么？",
            title="任务备注",
            default_text=self.current_task,
            ok="确定",
            cancel="取消",
            dimensions=(320, 80),
        ).run()
        
        if response.clicked:
            self.current_task = response.text.strip()
            if self.state in ("working", "paused"):
                self._update_title()
                self._save_state()
            self._notify("📋 任务已设置", self.current_task)
    
    # ─── 偏好设置 ───────────────────────────────────────
    def _preferences(self, _=None):
        """打开偏好设置窗口"""
        cfg = self.config
        response = rumps.Window(
            message=(
                f"工作时间（分钟）：\n"
                f"短休息（分钟）：\n"
                f"长休息（分钟）：\n"
                f"长休息间隔（几个番茄后）：\n"
                f"工作结束自动休息（1=是/0=否）：\n"
                f"休息结束自动工作（1=是/0=否）："
            ),
            title="🍅 番茄钟设置",
            default_text=(
                f"{cfg['work_duration']}\n"
                f"{cfg['short_break']}\n"
                f"{cfg['long_break']}\n"
                f"{cfg['long_break_interval']}\n"
                f"{1 if cfg['auto_start_break'] else 0}\n"
                f"{1 if cfg['auto_start_work'] else 0}"
            ),
            ok="保存",
            cancel="取消",
            dimensions=(300, 200),
        ).run()
        
        if response.clicked:
            try:
                lines = response.text.strip().split("\n")
                if len(lines) >= 6:
                    new_cfg = {
                        "work_duration": max(1, min(120, int(lines[0]))),
                        "short_break": max(1, min(30, int(lines[1]))),
                        "long_break": max(1, min(60, int(lines[2]))),
                        "long_break_interval": max(1, min(10, int(lines[3]))),
                        "auto_start_break": bool(int(lines[4])),
                        "auto_start_work": bool(int(lines[5])),
                        "sound_enabled": cfg.get("sound_enabled", True),
                    }
                    self.config = new_cfg
                    self._save_config()
                    self._build_menu()  # 重建菜单以更新时长显示
                    self._notify("✅ 设置已保存", 
                                f"工作{new_cfg['work_duration']}分钟 | 短休{new_cfg['short_break']}分钟 | 长休{new_cfg['long_break']}分钟")
            except ValueError:
                self._notify("❌ 设置格式错误", "请输入数字")
    
    # ─── 辅助功能 ───────────────────────────────────────
    def _today_stats_text(self):
        """今日统计文本"""
        hours = self.total_work_seconds / 3600
        return f"📊 今日：{hours:.1f}小时 | {self.today_pomodoros}个🍅"
    
    def _open_data_folder(self, _=None):
        """在 Finder 中打开数据文件夹"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.system(f'open "{DATA_DIR}"')
    
    def _quit_app(self, _=None):
        """退出应用"""
        if self.state in ("working", "breaking", "paused"):
            response = rumps.alert(
                title="确定退出？",
                message="当前有正在进行的番茄钟，退出后将丢失进度。",
                ok="退出",
                cancel="取消",
            )
            if response != 1:
                return
            # 如果还在工作状态，记录已用时间
            if self.state in ("working", "paused") and self.current_type == "work":
                elapsed = (datetime.datetime.now() - self.session_start).total_seconds()
                actual = self._get_duration_seconds() - self.remaining_seconds
                if self.state == "paused":
                    actual = self._get_duration_seconds() - self.remaining_seconds
                if actual > 30:
                    self._log_session(self.session_start, datetime.datetime.now(),
                                    int(actual), self.current_task, completed=False)
        
        STATE_PATH.unlink(missing_ok=True)
        rumps.quit_application()


# ─── 启动 ───────────────────────────────────────────────
if __name__ == "__main__":
    app = PomodoroApp()
    app.run()
