import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import StrMethodFormatter

_FONT = Path(__file__).with_name("assets") / "xkcd-script.ttf"
font_manager.fontManager.addfont(_FONT)
_HANDWRITING_FONT = font_manager.FontProperties(fname=_FONT)

_BLUE = "#0072B2"
_GRAY = "#6B7280"
_ORANGE = "#D55E00"
_GRID = "#E5E7EB"


def make_chart(current_participants, current_leaders, historical, *, comparison_label="Historical", today_days_before=0):
    days = sorted(set(current_participants) | set(current_leaders or {}) | set(historical), reverse=True)
    historical_days = sorted(historical, reverse=True)
    panels = [("participants", current_participants, 0)]
    if current_leaders is not None: panels.append(("mentor / judges", current_leaders, 1))

    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 12}):
        fig, axes = plt.subplots(len(panels), 1, sharex=True, figsize=(8, 3.4 * len(panels)), constrained_layout=True, squeeze=False)
        for ax, (label, current, index) in zip(axes[:, 0], panels):
            if historical_days:
                values = [historical[d][index] for d in historical_days]
                ax.plot(historical_days, values, "--", color=_GRAY, linewidth=1.8)
                ax.annotate(comparison_label, (historical_days[-1], values[-1]), xytext=(-8, 8), textcoords="offset points", ha="right", color=_GRAY)
            present = [d for d in days if d in current]
            ax.plot(present, [current[d] for d in present], color=_BLUE, linewidth=2.5)
            ax.axvline(today_days_before, color=_ORANGE, linewidth=1.5, linestyle=":")
            if ax is axes[0, 0]:
                ax.text(today_days_before, 1.01, "today", transform=ax.get_xaxis_transform(), ha="center", va="bottom", color=_ORANGE, fontproperties=_HANDWRITING_FONT)
            if today_days_before in current:
                value = current[today_days_before]
                ax.annotate(f"current: {value:,}", (today_days_before, value), xytext=(10, 8), textcoords="offset points", color=_BLUE, fontproperties=_HANDWRITING_FONT)
            ax.set_ylabel(label, fontproperties=_HANDWRITING_FONT)
            ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            for tick in ax.get_yticklabels(): tick.set_fontproperties(_HANDWRITING_FONT)
            ax.spines[["top", "right"]].set_visible(False)
            ax.spines["bottom"].set_color(_GRID)
            ax.spines["bottom"].set_linewidth(1.2)
            ax.grid(axis="y", color=_GRID, linewidth=0.8)
            ax.set_axisbelow(True)
            ax.tick_params(length=0)
            ax.margins(y=.14)

        axes[-1, 0].set_xlabel("days before event", fontproperties=_HANDWRITING_FONT)
        for tick in axes[-1, 0].get_xticklabels(): tick.set_fontproperties(_HANDWRITING_FONT)
        axes[-1, 0].invert_xaxis()
        output = io.BytesIO()
        fig.savefig(output, format="png", dpi=160, facecolor="white")
        plt.close(fig)
        return output.getvalue()
