# 🍅 Pomodoro Timer

macOS 菜单栏番茄钟，工作数据实时同步到 iCloud，支持 AI 助手读取统计。

![](https://img.shields.io/badge/platform-macOS-lightgrey) ![](https://img.shields.io/badge/python-3.10+-blue)

## ✨ 功能

- 🍅 **菜单栏倒计时** — 鼠标一点就能看到剩余时间
- ⏯ **暂停/继续** — 随时中断，随时恢复
- 📋 **任务备注** — 每个番茄钟标注在做什么
- 🔔 **系统通知** — 会话结束时弹窗 + 提示音
- 📊 **工时统计** — 今日、本周、月度汇总
- ☁️ **iCloud 同步** — 数据实时写入 iCloud，多设备可读
- 🤖 **AI 可读** — 配套 `stats.py`，AI 助手可直接读取数据

## 📦 安装

```bash
# 克隆仓库
git clone https://github.com/xxzhuu/pomodoro.git
cd pomodoro

# 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install rumps pyobjc-framework-UserNotifications

# 启动
python3 pomodoro.py
```

## 🖥 macOS 窗口版 App

项目也提供原生 macOS 窗口界面，并已在仓库中包含打包好的 `dist/Pomodoro.app`。

克隆后可以直接打开：

```bash
open dist/Pomodoro.app
```

如果你修改了源码，可以重新构建：

```bash
./build_app.sh
```

窗口版支持：
- 大倒计时和进度条
- 任务备注输入
- 开始工作、短休息、长休息、暂停、结束
- 今日统计
- 自动休息、自动开始工作、提示音开关
- 偏好设置和打开数据文件夹

## 🚀 开机自启

```bash
# 编辑 plist 中的路径，然后：
cp com.emily.pomodoro.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.emily.pomodoro.plist
```

## 📁 数据结构

工作记录存储在 `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Auty/番茄钟/`

```
番茄钟/
├── 2026-06-06.json    # 机器可读（供 AI 分析）
└── 2026-06-06.md      # 人类可读（Obsidian 日报）
```

### JSON 格式

```json
{
  "date": "2026-06-06",
  "sessions": [
    {
      "start": "09:00:00",
      "end": "09:25:00",
      "duration_minutes": 25.0,
      "task": "设计稿修改",
      "completed": true
    }
  ],
  "total_work_minutes": 150.0,
  "total_pomodoros": 6
}
```

## 🤖 AI 助手集成

AI 助手（如 Emily）可以通过 `stats.py` 直接读取工作数据：

```python
from stats import get_today_stats, get_week_stats, get_month_stats

# 今日工时
today = get_today_stats()
print(today['total_hours'])   # 2.5
print(today['pomodoros'])     # 6

# 本周汇总
week = get_week_stats()
print(week['total_hours'])    # 15.0

# 月度报告
month = get_month_stats()
print(month['days_with_work']) # 18
```

或命令行：

```bash
python3 stats.py today    # 今日统计
python3 stats.py week     # 本周汇总
python3 stats.py month    # 月度报告
python3 stats.py recent   # 最近7天趋势
```

## ⌨️ 快捷键

| 操作 | 说明 |
|------|------|
| 点击菜单栏 🍅 | 展开菜单 |
| `▶ 开始工作` | 开始 25 分钟番茄钟 |
| `☕ 短休息` | 5 分钟休息 |
| `🛌 长休息` | 15 分钟休息 |
| `⏸ 暂停` | 暂停当前计时 |
| `📋 设置任务备注` | 输入任务描述 |

## ⚙️ 配置

通过菜单栏 `⚙️ 偏好设置` 可自定义：
- 工作时长（默认 25 分钟）
- 短休息时长（默认 5 分钟）
- 长休息时长（默认 15 分钟）
- 长休息间隔（默认 4 个番茄）
- 自动切换工作/休息

## 📄 License

MIT
