#!/usr/bin/env python
"""Recompute the versioned Plotly snapshot for china-excavator-macro-trends."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from inv import viz
from inv.reporting import ReportWriter

writer = ReportWriter()
viz.setup_plotly()

ROOT = Path(__file__).resolve().parents[2]
MONTHLY_DATA = ROOT / "data/raw/cn_macro/excavator_macro_monthly.csv"
DEMAND_MONTHLY_DATA = ROOT / "data/raw/cn_macro/excavator_demand_monthly.csv"
monthly = pd.read_csv(MONTHLY_DATA, parse_dates=["date"]).set_index("date")
demand_monthly = pd.read_csv(DEMAND_MONTHLY_DATA, parse_dates=["date"]).set_index("date")

def zscore(series: pd.Series) -> pd.Series:
    return (series - series.mean()) / series.std(ddof=0)

# --- fig-output-pmi-li-keqiang ---
fig = go.Figure()

excavator_contribution = monthly["excavator_output_units"].copy()
combined = monthly["excavator_jan_feb_combined_units"].dropna()
for date, value in combined.items():
    excavator_contribution.loc[date - pd.offsets.MonthBegin(1)] = 0.0
    excavator_contribution.loc[date] = value

excavator_trailing_12m = excavator_contribution.rolling(12, min_periods=12).sum()
excavator_yoy = excavator_trailing_12m.pct_change(12, fill_method=None) * 100
# 不展示为滚动计算而设置的 1 月零值；2 月点使用公开的 1—2 月合计。
excavator_yoy = excavator_yoy.loc[
    monthly["excavator_output_units"].notna()
    | monthly["excavator_jan_feb_combined_units"].notna()
].dropna()
pmi_rolling = monthly["manufacturing_pmi"].rolling(12, min_periods=12).mean().dropna()
li_keqiang_rolling = (
    monthly["li_keqiang_index_yoy_pct_digitized"]
    .dropna()
    .rolling(12, min_periods=12)
    .mean()
    .dropna()
)

series_1 = [
    (excavator_yoy, "挖掘机产量同比", "#2563EB", "solid", "%{customdata:+.1f}%"),
    (pmi_rolling, "制造业 PMI", "#D4A017", "dash", "%{customdata:.1f} 点"),
    (li_keqiang_rolling, "克强指数", "#059669", "dot", "%{customdata:.1f}%"),
]

for series, label, color, dash, raw_format in series_1:
    fig.add_trace(go.Scatter(
        x=series.index,
        y=zscore(series),
        customdata=series,
        mode="lines",
        name=label,
        connectgaps=True,
        line=dict(color=color, width=2.5, dash=dash),
        hovertemplate=f"%{{x|%Y-%m}}<br>{label}：{raw_format}<br>标准化值：%{{y:+.2f}}<extra></extra>",
    ))

fig.add_hline(y=0, line=dict(color="#9CA3AF", width=1, dash="dot"))
fig.update_layout(
    xaxis=dict(
        title="月份",
        type="date",
        tickformat="%Y",
        dtick="M24",
        range=["2005-01-01", "2026-08-01"],
    ),
    yaxis=dict(title="标准化值（Z-score）", zeroline=False),
)
writer.write_plotly(fig, 'output-pmi-li-keqiang')

# --- fig-excavator-demand-drivers ---
sales_ytd = demand_monthly["excavator_sales_units"].groupby(
    demand_monthly.index.year
).cumsum()
sales_ytd_yoy = sales_ytd.pct_change(12, fill_method=None) * 100
# 投资与房地产月报通常不单独发布 1 月累计数据；销量也从 2 月起展示，
# 让四条线使用一致的发布频率，再分别对 12 个已公布观测取滚动均值。
sales_ytd_yoy = sales_ytd_yoy.loc[sales_ytd_yoy.index.month != 1]

series_2 = [
    (sales_ytd_yoy, "挖掘机销量", "#2563EB", "solid"),
    (
        demand_monthly["real_estate_new_starts_ytd_yoy_pct"],
        "房地产新开工面积",
        "#DC2626",
        "solid",
    ),
    (
        demand_monthly["infrastructure_investment_ytd_yoy_pct"],
        "基建投资",
        "#059669",
        "dash",
    ),
    (
        demand_monthly["mining_investment_ytd_yoy_pct"],
        "采矿业投资",
        "#EA580C",
        "dot",
    ),
]

fig = go.Figure()
for series, label, color, dash in series_2:
    rolling = series.dropna().rolling(12, min_periods=12).mean().dropna()
    fig.add_trace(go.Scatter(
        x=rolling.index,
        y=rolling,
        mode="lines",
        name=label,
        connectgaps=False,
        line=dict(color=color, width=2.4, dash=dash),
        hovertemplate=f"%{{x|%Y-%m}}<br>{label}：%{{y:+.1f}}%<extra></extra>",
    ))

fig.add_hline(y=0, line=dict(color="#6B7280", width=1, dash="dash"))
fig.update_layout(
    xaxis=dict(
        title="月份",
        type="date",
        tickformat="%Y",
        dtick="M24",
        range=["2015-01-01", "2026-01-01"],
    ),
    yaxis=dict(title="累计同比的 12 期滚动均值（%）", ticksuffix="%", zeroline=False),
)
writer.write_plotly(fig, 'excavator-demand-drivers')

writer.finish()
