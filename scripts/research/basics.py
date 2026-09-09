#!/usr/bin/env python
"""Generate the teaching charts for the time-series basics chapter."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from inv import viz
from inv.reporting import ReportWriter

writer = ReportWriter()
viz.setup_plotly()

BLUE = "#2563EB"
GOLD = "#D4A017"
ORANGE = "#C45A25"
INK = "#374151"
MUTED = "#6B7280"
GRID = "#E5E7EB"


# All values in this script are deliberately small, synthetic teaching data.
sales_index = pd.date_range("2023-01-01", "2025-12-01", freq="MS")
sales = pd.Series(
    [
        80, 84, 90, 96, 100, 104, 108, 112, 116, 120, 126, 140,
        88, 92, 99, 106, 110, 114, 118, 80, 105, 118, 132, 150,
        90, 95, 101, 109, 114, 117, 120, 100, 115, 126, 140, 160,
    ],
    index=sales_index,
    dtype="float64",
)
sales_yoy = sales.pct_change(12, fill_method=None) * 100
sales_ytd = sales.groupby(sales.index.year).cumsum()
sales_ytd_yoy = sales_ytd.pct_change(12, fill_method=None) * 100
sales_r12m = sales.rolling(12, min_periods=12).sum()
sales_r12m_yoy = sales_r12m.pct_change(12, fill_method=None) * 100
sales_2025 = sales.loc["2025-01-01":"2025-12-01"].index

fig = go.Figure()
for values, name, color, dash in [
    (sales_yoy, "当期值同比", BLUE, "solid"),
    (sales_ytd_yoy, "YTD 同比", GOLD, "dash"),
    (sales_r12m_yoy, "R12M 同比", MUTED, "dot"),
]:
    selected = values.loc[sales_2025]
    fig.add_trace(go.Scatter(
        x=selected.index,
        y=selected,
        mode="lines+markers",
        name=name,
        line=dict(color=color, width=2.5, dash=dash),
        marker=dict(size=6, symbol="circle"),
        hovertemplate=f"%{{x|%Y-%m}}<br>{name}：%{{y:.2f}}%<extra></extra>",
    ))

fig.add_hline(y=0, line=dict(color="#9CA3AF", width=1, dash="dash"))
fig.add_annotation(
    x=pd.Timestamp("2025-08-01"),
    y=float(sales_yoy.loc["2025-08-01"]),
    text="上年低基数<br>当期同比 25%",
    showarrow=True,
    arrowhead=0,
    arrowcolor=INK,
    ax=42,
    ay=-46,
    font=dict(color=INK, size=11),
    bgcolor="rgba(255,255,255,0.88)",
    borderpad=3,
)
fig.update_layout(
    hovermode="x unified",
    legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom"),
    xaxis=dict(
        title="2025 年月份",
        type="date",
        tickformat="%m月",
        dtick="M1",
        range=["2024-12-20", "2025-12-12"],
    ),
    yaxis=dict(title="同比增速（%）", ticksuffix="%", range=[-3, 29], zeroline=False),
)
writer.write_plotly(fig, "sales-growth-comparison")


# A stock-flow bridge: gross flows explain why the ending stock changes by less.
fig = go.Figure(go.Waterfall(
    orientation="v",
    measure=["absolute", "relative", "relative", "relative", "relative", "total"],
    x=["期初", "投放", "偿还", "核销", "估值", "期末"],
    y=[1000, 120, -60, -15, 5, 0],
    text=["1,000", "+120", "−60", "−15", "+5", "1,050"],
    textposition="outside",
    increasing=dict(marker=dict(color=BLUE, line=dict(color=BLUE, width=1))),
    decreasing=dict(marker=dict(color=ORANGE, line=dict(color=ORANGE, width=1))),
    totals=dict(marker=dict(color="#D1D5DB", line=dict(color=INK, width=1.2))),
    connector=dict(line=dict(color="#9CA3AF", width=1, dash="dot")),
    hovertemplate="%{x}<br>变动或余额：%{text} 亿元<extra></extra>",
    cliponaxis=False,
))
fig.update_layout(
    showlegend=False,
    xaxis=dict(title="2025 年上半年余额变动项目", tickangle=0, tickfont=dict(size=10)),
    yaxis=dict(title="亿元", range=[0, 1210], gridcolor=GRID, zeroline=False),
    margin=dict(l=60, r=34, t=60, b=66),
)
writer.write_plotly(fig, "loan-balance-bridge")


# CPI level and rate panels: the level can rise while year-over-year inflation falls.
cpi_index = pd.date_range("2024-01-01", "2025-12-01", freq="MS")
cpi = pd.Series(
    [
        100.0, 100.5, 101.0, 101.5, 102.0, 102.5,
        103.0, 103.5, 104.0, 104.5, 105.0, 105.5,
        105.7, 105.9, 106.1, 106.3, 106.5, 106.7,
        106.9, 107.1, 107.3, 107.5, 107.7, 107.9,
    ],
    index=cpi_index,
    dtype="float64",
)
cpi_mom = cpi.pct_change(fill_method=None) * 100
cpi_yoy = cpi.pct_change(12, fill_method=None) * 100

fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.15,
    subplot_titles=("CPI 指数水平", "2025 年环比与同比"),
)
fig.add_trace(go.Scatter(
    x=cpi.index,
    y=cpi,
    mode="lines+markers",
    name="CPI 指数",
    line=dict(color=BLUE, width=2.5),
    marker=dict(size=5),
    hovertemplate="%{x|%Y-%m}<br>CPI：%{y:.1f}<extra></extra>",
), row=1, col=1)
fig.add_trace(go.Scatter(
    x=cpi_yoy.loc["2025-01-01":].index,
    y=cpi_yoy.loc["2025-01-01":],
    mode="lines+markers",
    name="同比",
    line=dict(color=GOLD, width=2.5, dash="solid"),
    marker=dict(size=5),
    hovertemplate="%{x|%Y-%m}<br>同比：%{y:.2f}%<extra></extra>",
), row=2, col=1)
fig.add_trace(go.Scatter(
    x=cpi_mom.loc["2025-01-01":].index,
    y=cpi_mom.loc["2025-01-01":],
    mode="lines+markers",
    name="环比",
    line=dict(color=BLUE, width=2, dash="dot"),
    marker=dict(size=5, symbol="circle-open"),
    hovertemplate="%{x|%Y-%m}<br>环比：%{y:.2f}%<extra></extra>",
), row=2, col=1)
fig.update_yaxes(title_text="指数点", range=[99.4, 108.5], row=1, col=1)
fig.update_yaxes(title_text="变化率（%）", ticksuffix="%", range=[0, 6.3], row=2, col=1)
fig.update_xaxes(
    title_text="月份",
    type="date",
    tickformat="%Y-%m",
    dtick="M3",
    range=["2023-12-15", "2025-12-15"],
    row=2,
    col=1,
)
fig.update_layout(
    hovermode="x unified",
    legend=dict(orientation="h", x=0, y=1.05, xanchor="left", yanchor="bottom"),
    margin=dict(l=64, r=34, t=72, b=56),
)
writer.write_plotly(fig, "cpi-level-and-inflation")

writer.finish()
