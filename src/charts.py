"""生成7天健康趋势图表。"""

from pathlib import Path
from src import config

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.font_manager as fm
    from datetime import datetime
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def _ensure_cjk_font():
    """确保中文字体可用。优先系统字体，fallback 到下载 Noto Sans CJK。"""
    # 优先尝试系统已有的中文字体
    system_fonts = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "SimHei",
                    "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Noto Sans SC"]
    for font_name in system_fonts:
        matches = [f for f in fm.fontManager.ttflist if font_name in f.name]
        if matches:
            plt.rcParams["font.sans-serif"] = [font_name, "sans-serif"]
            plt.rcParams["axes.unicode_minus"] = False
            return

    # Ubuntu/CI 环境：下载 Noto Sans SC
    font_dir = config.DATA_DIR / "fonts"
    font_path = font_dir / "NotoSansSC-Regular.ttf"
    if not font_path.exists():
        import urllib.request
        font_dir.mkdir(parents=True, exist_ok=True)
        url = "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"
        print(f"[Chart] Downloading CJK font...")
        urllib.request.urlretrieve(url, str(font_path))
        print(f"[Chart] Font saved to {font_path}")

    fm.fontManager.addfont(str(font_path))
    font_prop = fm.FontProperties(fname=str(font_path))
    plt.rcParams["font.sans-serif"] = [font_prop.get_name(), "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False


def generate_weekly_chart(recent_7: list, output_path=None) -> Path:
    """生成7天趋势图（恢复分 + HRV + 睡眠时长），返回图片路径。"""
    if not HAS_MPL:
        raise ImportError("matplotlib not installed")

    output_path = output_path or config.DATA_DIR / "weekly_chart.png"

    # 按日期升序排列
    rows = sorted(recent_7, key=lambda r: r.get("date", ""))

    dates = []
    recovery = []
    hrv = []
    sleep_hours = []
    deep_sleep_hours = []
    strain = []

    for r in rows:
        d = r.get("date")
        if not d:
            continue
        dates.append(datetime.strptime(d, "%Y-%m-%d"))
        recovery.append(r.get("recovery_score"))
        hrv.append(r.get("hrv"))
        sleep_h = r.get("sleep_total_min")
        sleep_hours.append(round(sleep_h / 60, 1) if sleep_h else None)
        deep_h = r.get("sleep_deep_min")
        deep_sleep_hours.append(round(deep_h / 60, 1) if deep_h else None)
        strain.append(r.get("strain"))

    if len(dates) < 2:
        return None

    # 设置中文字体（兼容 macOS / Ubuntu CI）
    _ensure_cjk_font()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("📊 过去 7 天健康趋势", fontsize=18, fontweight="bold", y=0.98)
    fig.patch.set_facecolor("#FAFAFA")

    colors = {
        "recovery": "#4CAF50",
        "hrv": "#2196F3",
        "sleep": "#9C27B0",
        "deep": "#E91E63",
        "strain": "#FF9800",
    }

    def _plot(ax, x, y, label, color, ylabel, fill=True):
        valid_x = [xi for xi, yi in zip(x, y) if yi is not None]
        valid_y = [yi for yi in y if yi is not None]
        if not valid_x:
            ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", transform=ax.transAxes, fontsize=14, color="gray")
            return
        ax.plot(valid_x, valid_y, "-o", color=color, linewidth=2.5, markersize=8, label=label)
        if fill:
            ax.fill_between(valid_x, valid_y, alpha=0.15, color=color)
        # 标注数值
        for xi, yi in zip(valid_x, valid_y):
            ax.annotate(f"{yi:.0f}" if yi == int(yi) else f"{yi:.1f}",
                        (xi, yi), textcoords="offset points", xytext=(0, 12),
                        ha="center", fontsize=10, fontweight="bold", color=color)
        # 均值线
        avg_val = sum(valid_y) / len(valid_y)
        ax.axhline(y=avg_val, color=color, linestyle="--", alpha=0.4, linewidth=1)
        ax.text(valid_x[-1], avg_val, f" 均值 {avg_val:.1f}", color=color, alpha=0.6, fontsize=9, va="bottom")
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(label, fontsize=14, fontweight="bold", pad=10)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.grid(True, alpha=0.2)
        ax.set_facecolor("#FFFFFF")

    # 恢复分
    _plot(axes[0, 0], dates, recovery, "恢复分 (%)", colors["recovery"], "%")
    # 添加区域色带
    if any(r is not None for r in recovery):
        axes[0, 0].axhspan(67, 100, alpha=0.08, color="green", label="绿区")
        axes[0, 0].axhspan(34, 67, alpha=0.08, color="yellow", label="黄区")
        axes[0, 0].axhspan(0, 34, alpha=0.08, color="red", label="红区")
        axes[0, 0].set_ylim(0, 105)

    # HRV
    _plot(axes[0, 1], dates, hrv, "HRV (ms)", colors["hrv"], "ms")

    # 睡眠时长（含深睡对比）
    ax_sleep = axes[1, 0]
    valid_dates_s = [d for d, s in zip(dates, sleep_hours) if s is not None]
    valid_sleep = [s for s in sleep_hours if s is not None]
    valid_dates_d = [d for d, s in zip(dates, deep_sleep_hours) if s is not None]
    valid_deep = [s for s in deep_sleep_hours if s is not None]
    if valid_dates_s:
        ax_sleep.bar(valid_dates_s, valid_sleep, width=0.5, color=colors["sleep"], alpha=0.6, label="总睡眠")
        if valid_dates_d:
            ax_sleep.bar(valid_dates_d, valid_deep, width=0.5, color=colors["deep"], alpha=0.8, label="深度睡眠")
        for xi, yi in zip(valid_dates_s, valid_sleep):
            ax_sleep.text(xi, yi + 0.1, f"{yi:.1f}h", ha="center", fontsize=9, fontweight="bold", color=colors["sleep"])
        ax_sleep.axhline(y=7, color="gray", linestyle="--", alpha=0.4)
        ax_sleep.text(valid_dates_s[-1], 7, " 目标 7h", color="gray", alpha=0.6, fontsize=9, va="bottom")
        ax_sleep.legend(fontsize=10)
    else:
        ax_sleep.text(0.5, 0.5, "暂无数据", ha="center", va="center", transform=ax_sleep.transAxes, fontsize=14, color="gray")
    ax_sleep.set_ylabel("小时", fontsize=12)
    ax_sleep.set_title("睡眠时长", fontsize=14, fontweight="bold", pad=10)
    ax_sleep.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax_sleep.grid(True, alpha=0.2)
    ax_sleep.set_facecolor("#FFFFFF")

    # 压力分
    _plot(axes[1, 1], dates, strain, "压力负荷 (Strain)", colors["strain"], "分")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[Chart] Saved to {output_path}")
    return output_path
