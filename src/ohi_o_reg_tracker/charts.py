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


def make_chart(current_participants, current_leaders, historical, *, comparison_label="Historical", today_days_before=0, participant_histories=None):
    participant_histories = participant_histories or {
        comparison_label: {day: values[0] for day, values in historical.items()}
    }
    days = set(current_participants) | set(current_leaders or {}) | set(historical)
    days.update(day for values in participant_histories.values() for day in values)
    days = sorted(days, reverse=True)
    panels = [("participants", current_participants, 0)]
    if current_leaders is not None:
        panels.append(("mentor / judges", current_leaders, 1))

    with plt.rc_context({
        "font.family": "DejaVu Sans",
        "font.size": 10.5,
        "axes.labelsize": 10.5,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
    }):
        fig, axes = plt.subplots(
            len(panels), 1,
            sharex=True,
            figsize=(8.5, 3.25 * len(panels)),
            constrained_layout=True,
            squeeze=False,
        )
        for ax, (label, current, index) in zip(axes[:, 0], panels):
            histories = participant_histories if index == 0 else {
                comparison_label: {day: values[1] for day, values in historical.items()}
            }
            for history_index, (history_label, values_by_day) in enumerate(histories.items()):
                history_days = sorted(values_by_day, reverse=True)
                if not history_days:
                    continue
                color, linestyle = ((_GRAY, "--"), ("#009E73", ":"))[history_index % 2]
                values = [values_by_day[day] for day in history_days]
                ax.plot(history_days, values, linestyle, color=color, linewidth=1.6, solid_capstyle="round")
                ax.annotate(history_label, (history_days[-1], values[-1]), xytext=(-8, 8 + 14 * history_index), textcoords="offset points", ha="right", color=color, fontsize=9, fontproperties=_HANDWRITING_FONT)
            # Smaller values are closer to event day; never draw current data past today.
            present = [day for day in days if day >= today_days_before and day in current]
            ax.plot(present, [current[day] for day in present], color=_BLUE, linewidth=2.7, solid_capstyle="round")
            ax.axvline(today_days_before, color=_ORANGE, linewidth=1.4, linestyle=(0, (2, 3)))
            if ax is axes[0, 0]:
                ax.text(today_days_before, 1.01, "today", transform=ax.get_xaxis_transform(), ha="center", va="bottom", color=_ORANGE, fontsize=9, fontproperties=_HANDWRITING_FONT)
            if today_days_before in current:
                value = current[today_days_before]
                ax.annotate(
                    f"current: {value:,}",
                    (today_days_before, value),
                    xytext=(-10, 10),
                    textcoords="offset points",
                    ha="right",
                    color=_BLUE,
                    fontsize=9,
                    fontproperties=_HANDWRITING_FONT,
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
                )
            ax.set_ylabel(label, labelpad=10, fontproperties=_HANDWRITING_FONT)
            ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            for tick in ax.get_yticklabels():
                tick.set_fontproperties(_HANDWRITING_FONT)
            ax.spines[["top", "right"]].set_visible(False)
            ax.spines["bottom"].set_color(_GRID)
            ax.spines["bottom"].set_linewidth(1.0)
            ax.grid(axis="y", color=_GRID, linewidth=0.7)
            ax.set_axisbelow(True)
            ax.tick_params(length=0)
            ax.margins(y=.14)

        axes[-1, 0].set_xlabel("days before event", labelpad=8, fontproperties=_HANDWRITING_FONT)
        for tick in axes[-1, 0].get_xticklabels():
            tick.set_fontproperties(_HANDWRITING_FONT)
        axes[-1, 0].invert_xaxis()
        output = io.BytesIO()
        fig.savefig(output, format="png", dpi=220, facecolor="white")
        plt.close(fig)
        return output.getvalue()
