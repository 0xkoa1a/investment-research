"""统一图表样式：Plotly 交互图表与 matplotlib 辅助统计。

分工:
  Plotly     -> 探索与阅读，可缩放/悬停看数值；研究脚本写出标准 JSON 快照
  matplotlib -> 仅用于需要的统计辅助，不负责站点产物

中文字体: macOS 自带 PingFang/STHeiti/Songti，本模块自动探测可用字体，
避免图表中文显示为方框（这是 matplotlib 在中文环境最常见的坑）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from inv.storage import log

# ---------------------------------------------------------------------------
# 配色（统一视觉语言，同一资产在所有图中颜色一致）
# ---------------------------------------------------------------------------

COLORS: dict[str, str] = {
    "gold": "#D4A017",
    "silver": "#9CA3AF",
    "dxy": "#2563EB",
    "usd_broad": "#1E40AF",
    "real10y": "#DC2626",
    "ust10y": "#EA580C",
    "ust2y": "#F59E0B",
    "breakeven10y": "#7C3AED",
    "ffr_effective": "#111827",
    "spx": "#059669",
    "ndx": "#10B981",
    "tlt": "#0891B2",
    "csi300": "#DB2777",
    "sse": "#BE185D",
    "wti": "#57534E",
    "vix": "#991B1B",
}

PALETTE = ["#2563EB", "#D4A017", "#DC2626", "#059669", "#7C3AED", "#EA580C", "#0891B2", "#DB2777"]


def color_of(name: str, fallback_idx: int = 0) -> str:
    """取字段的固定配色；未登记则从调色板轮转。"""
    key = name.replace("ret_", "").replace("d_", "")
    return COLORS.get(key, PALETTE[fallback_idx % len(PALETTE)])


# ---------------------------------------------------------------------------
# 中文字体（matplotlib）
# ---------------------------------------------------------------------------

_CJK_CANDIDATES = [
    "PingFang SC",
    "PingFang HK",
    "Hiragino Sans GB",
    "STHeiti",
    "Heiti SC",
    "Songti SC",
    "Arial Unicode MS",
    "Noto Sans CJK SC",
]

_font_ready = False


def setup_matplotlib() -> str | None:
    """配置 matplotlib 全局样式与中文字体。

    Returns:
        实际启用的中文字体名；未找到返回 None。
    """
    global _font_ready
    import matplotlib
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((f for f in _CJK_CANDIDATES if f in available), None)

    matplotlib.rcParams.update(
        {
            "figure.figsize": (11, 5.5),
            "figure.dpi": 110,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "semibold",
            "axes.labelsize": 11,
            "axes.grid": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
            "legend.frameon": False,
            "lines.linewidth": 1.5,
            # 中文字体下负号会显示异常，必须关闭 unicode_minus
            "axes.unicode_minus": False,
        }
    )

    if chosen:
        matplotlib.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
        if not _font_ready:
            log("ok", f"matplotlib 中文字体: {chosen}")
    else:
        log("warn", f"未找到中文字体，图表中文可能显示为方框。候选: {_CJK_CANDIDATES}")

    _font_ready = True
    return chosen


# ---------------------------------------------------------------------------
# Plotly 模板
# ---------------------------------------------------------------------------


def setup_plotly() -> None:
    """注册并启用统一的 Plotly 模板。"""
    import plotly.graph_objects as go
    import plotly.io as pio

    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        font=dict(family="PingFang SC, Helvetica Neue, Arial, sans-serif", size=12, color="#1F2937"),
        colorway=PALETTE,
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="x unified",
        margin=dict(l=60, r=60, t=60, b=50),
        xaxis=dict(showgrid=True, gridcolor="#E5E7EB", gridwidth=1, zeroline=False, showspikes=True, spikethickness=1, spikedash="dot", spikecolor="#9CA3AF", spikemode="across"),
        yaxis=dict(showgrid=True, gridcolor="#E5E7EB", gridwidth=1, zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    pio.templates["inv"] = tpl
    pio.templates.default = "plotly_white+inv"


# ---------------------------------------------------------------------------
# Plotly 图表
# ---------------------------------------------------------------------------


def line_dual_axis(
    df: pd.DataFrame,
    left: list[str],
    right: list[str],
    *,
    left_title: str = "",
    right_title: str = "",
    labels: dict[str, str] | None = None,
):
    """双 Y 轴时间序列图（Plotly）。

    用于把量级差异很大的序列画在一起，例如金价（~2000）与实际利率（~2%）。

    Args:
        left/right: 左/右轴字段名列表。
        labels:     字段名 -> 显示名（中文）映射。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    setup_plotly()
    labels = labels or {}
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    for i, c in enumerate(left):
        if c not in df.columns:
            continue
        fig.add_trace(
            go.Scatter(x=df.index, y=df[c], name=labels.get(c, c), line=dict(color=color_of(c, i), width=1.6)),
            secondary_y=False,
        )

    for j, c in enumerate(right):
        if c not in df.columns:
            continue
        fig.add_trace(
            go.Scatter(x=df.index, y=df[c], name=labels.get(c, c), line=dict(color=color_of(c, j + len(left)), width=1.6, dash="dot")),
            secondary_y=True,
        )

    fig.update_yaxes(title_text=left_title, secondary_y=False)
    fig.update_yaxes(title_text=right_title, secondary_y=True, showgrid=False)
    return fig


def line_multi(
    df: pd.DataFrame,
    cols: list[str],
    *,
    y_title: str = "",
    labels: dict[str, str] | None = None,
    hline: float | None = None,
):
    """多线时间序列图（Plotly，单一 Y 轴）。

    Args:
        hline: 若指定，画一条水平参考线（如相关性图的 0 线）。
    """
    import plotly.graph_objects as go

    setup_plotly()
    labels = labels or {}
    fig = go.Figure()

    for i, c in enumerate(cols):
        if c not in df.columns:
            continue
        fig.add_trace(
            go.Scatter(x=df.index, y=df[c], name=labels.get(c, c), line=dict(color=color_of(c, i), width=1.6))
        )

    if hline is not None:
        fig.add_hline(y=hline, line=dict(color="#6B7280", width=1, dash="dash"))

    fig.update_layout(yaxis_title=y_title)
    return fig


def normalized_lines(
    df: pd.DataFrame,
    cols: list[str],
    *,
    base: int = 100,
    labels: dict[str, str] | None = None,
):
    """归一化对比图：所有序列起点归为 base，便于比较相对表现。"""
    sub = df[[c for c in cols if c in df.columns]].dropna(how="all")
    sub = sub.loc[sub.dropna().index.min():] if not sub.dropna().empty else sub
    norm = sub.div(sub.iloc[0]).mul(base)
    return line_multi(norm, list(norm.columns), y_title=f"归一化 (起点={base})", labels=labels)


def heatmap_corr(corr: pd.DataFrame, *, labels: dict[str, str] | None = None):
    """相关矩阵热力图（Plotly）。"""
    import plotly.graph_objects as go

    setup_plotly()
    labels = labels or {}
    names = [labels.get(c, c.replace("ret_", "").replace("d_", "")) for c in corr.columns]

    fig = go.Figure(
        go.Heatmap(
            z=corr.values,
            x=names,
            y=names,
            zmin=-1,
            zmax=1,
            colorscale="RdBu",
            reversescale=True,
            text=np.round(corr.values, 2),
            texttemplate="%{text}",
            textfont=dict(size=10),
            colorbar=dict(title="ρ"),
        )
    )
    return fig


# ---------------------------------------------------------------------------
# 表格
# ---------------------------------------------------------------------------


def md_table(df: pd.DataFrame, *, digits: int = 3, index_name: str = "") -> str:
    """DataFrame -> Markdown 表格字符串（供研究正文内联展示）。"""
    out = df.copy()
    num_cols = out.select_dtypes("number").columns
    out[num_cols] = out[num_cols].round(digits)
    if index_name:
        out.index.name = index_name
    return out.to_markdown()
