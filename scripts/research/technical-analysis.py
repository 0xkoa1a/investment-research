#!/usr/bin/env python
"""Deterministic teaching examples; no market data, network or strategy backtest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from inv import viz
from inv.reporting import ReportWriter

INK, BLUE, GOLD, ORANGE, MUTED = "#374151", "#2563EB", "#D4A017", "#C45A25", "#6B7280"
ROOT = Path(__file__).resolve().parents[2]


def path_series(anchors: list[tuple[int, float]]) -> pd.Series:
    periods = np.arange(anchors[0][0], anchors[-1][0] + 1)
    return pd.Series(np.interp(periods, *zip(*anchors, strict=True)), index=periods, dtype=float)


def ema(values: pd.Series, window: int) -> pd.Series:
    return values.ewm(span=window, adjust=False).mean()


def wilder(values: pd.Series, window: int = 14) -> pd.Series:
    """Leading unavailable observations are omitted; interior gaps are rejected."""
    out = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    if len(valid) < window:
        return out
    if values.loc[valid.index[0]:].isna().any():
        raise ValueError("教学序列不能含内部缺失值")
    current = float(valid.iloc[:window].mean())
    out.loc[valid.index[window - 1]] = current
    for index, value in valid.iloc[window:].items():
        current += (float(value) - current) / window
        out.loc[index] = current
    return out


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    changes = close.diff()
    up = wilder(changes.clip(lower=0), window)
    down = wilder(-changes.clip(upper=0), window)
    return 100 * up / (up + down).replace(0, np.nan)


def true_range(bars: pd.DataFrame) -> pd.Series:
    previous = bars.close.shift()
    return pd.concat([bars.high - bars.low, (bars.high - previous).abs(),
                      (bars.low - previous).abs()], axis=1).max(axis=1)


def ohlc(close: pd.Series, padding: float = 0.8) -> pd.DataFrame:
    opening = close.shift().fillna(close.iloc[0])
    return pd.DataFrame({"open": opening, "high": np.maximum(opening, close) + padding,
                         "low": np.minimum(opening, close) - padding, "close": close})


def indicators(close: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame({"close": close})
    for n in (12, 20, 26):
        frame[f"ema{n}"] = ema(close, n)
    for n in (20, 60):
        frame[f"sma{n}"] = close.rolling(n, min_periods=n).mean()
    frame["dif"] = frame.ema12 - frame.ema26
    frame["dea"] = ema(frame.dif, 9)
    frame["histogram"] = frame.dif - frame.dea
    frame["rsi14"] = rsi(close)
    return frame


def value_area(volumes: list[int], fraction: float = 0.7) -> tuple[int, int]:
    lo = hi = int(np.argmax(volumes))
    accumulated = volumes[lo]
    target = sum(volumes) * fraction
    while accumulated < target:
        below = volumes[lo - 1] if lo > 0 else -1
        above = volumes[hi + 1] if hi + 1 < len(volumes) else -1
        if below >= above:
            lo -= 1
            accumulated += volumes[lo]
        else:
            hi += 1
            accumulated += volumes[hi]
    return lo, hi


def aggregate_bars(bars: pd.DataFrame, periods: int) -> pd.DataFrame:
    """Aggregate complete, consecutive teaching periods; no calendar inference."""
    if periods < 1 or len(bars) % periods:
        raise ValueError("聚合输入必须包含完整教学周期")
    groups = np.arange(len(bars)) // periods + 1
    return bars.groupby(groups).agg(open=("open", "first"), high=("high", "max"),
                                     low=("low", "min"), close=("close", "last"))


def multi_timeframe_data() -> dict[str, pd.DataFrame]:
    anchors = [(0, 148), (15, 160), (45, 120), (70, 140), (105, 100),
               (135, 120), (170, 80), (176, 92), (180, 86), (186, 100),
               (190, 94), (196, 110), (200, 103), (206, 112), (210, 108)]
    close = path_series([(day * 4, price) for day, price in anchors])
    close.loc[825:] = [110.8, 109.8, 109.4, 110.5, 111, 109.8, 108.5, 109,
                       109.5, 108.2, 107.5, 108.5, 108.8, 107.8, 106.8, 108]
    hourly = ohlc(close, padding=0).loc[1:]
    daily = aggregate_bars(hourly, 4)
    weekly = aggregate_bars(daily, 5)
    return {"timeframe_hourly": hourly, "timeframe_daily": daily, "timeframe_weekly": weekly}


def teaching_data() -> dict[str, pd.DataFrame]:
    structure = path_series([(1, 100), (6, 110), (9, 104), (15, 118), (19, 111),
                             (25, 125), (29, 119), (34, 128), (37, 123), (41, 116),
                             (46, 122), (51, 112)])
    box = pd.Series([103, 105, 108, 106, 102, 100.8, 103, 107, 109, 106,
                     104, 101, 102, 106, 109, 107, 104, 106, 108, 109,
                     113, 115, 117, 116, 114.5, 113.5, 112.5, 111.2, 110.5, 112],
                    index=range(1, 31), dtype=float)
    breakout = ohlc(box, 0.4)
    breakout.loc[:20, "high"] = breakout.loc[:20, "high"].clip(upper=110)
    breakout.loc[6, "low"] = 100
    breakout.loc[9, "high"] = 110
    breakout.loc[23, "high"] = 118
    breakout.loc[30, "low"] = 109.8
    breakout["volume"] = [90, 100, 110, 100] * 5 + [200, 180, 170, 160, 130, 115, 100, 90, 80, 85]

    deep = path_series([(1, 100), (60, 106), (70, 108), (80, 100), (100, 116), (110, 110),
                        (130, 140), (138, 122), (142, 126), (149, 114.8), (150, 116)])
    position = indicators(deep).join(ohlc(deep).drop(columns="close"))
    position["tr"] = true_range(position)
    position["atr14"] = wilder(position.tr)
    position["distance_atr"] = (position.close - position.sma20) / position.atr14

    momentum = path_series([(1, 100), (80, 100), (100, 120), (110, 112),
                            (149, 125.5), (155, 123.6)])
    momentum.loc[:80] += 0.6 * np.sin(np.arange(80) * np.pi / 4)
    momentum.loc[80] = 100
    # Alternating advances and pullbacks preserve endpoints and create weaker RSI.
    for period in range(111, 149):
        momentum.loc[period] += 0.6 if period % 2 else -0.6
    momentum.loc[148] = 124.4
    momentum.loc[150:] = [124.8, 125.0, 124.2, 124.7, 124.0, 123.6]
    momentum_frame = indicators(momentum)

    bb = pd.Series(np.concatenate([
        100 + 3 * np.sin(np.arange(30) * np.pi / 5),
        100 + 0.35 * np.sin(np.arange(30) * np.pi / 3),
        100 + np.arange(1, 41) * 0.65 + 0.4 * np.sin(np.arange(40)),
    ]), index=range(1, 101))
    bands = pd.DataFrame({"close": bb, "middle": bb.rolling(20).mean(), "std": bb.rolling(20).std(ddof=0)})
    bands["upper"] = bands.middle + 2 * bands["std"]
    bands["lower"] = bands.middle - 2 * bands["std"]

    volume = [200, 400, 400, 300, 300, 900, 1200, 1700, 1200, 1000, 600, 400, 1000, 300, 100]
    profile = pd.DataFrame({"lower": np.arange(100, 130, 2), "upper": np.arange(102, 132, 2),
                            "price": np.arange(101, 131, 2), "volume": volume})
    lo, hi = value_area(volume)
    profile["value_area"] = (profile.index >= lo) & (profile.index <= hi)
    branches = pd.DataFrame(index=range(1, 28), columns=["history", "path_a", "path_b"], dtype=float)
    branches.loc[:21, "history"] = [103, 105, 108, 110, 107, 104, 101, 103, 107, 109.5,
                                     106, 103, 100.5, 104, 107, 110, 107, 105, 108, 109.5, 112]
    branches.loc[21:, "path_a"] = [112, 114, 111.8, 110.6, 112.6, 115, 116]
    branches.loc[21:, "path_b"] = [112, 108.8, 110.5, 108, 106, 105, 104]
    patterns = pd.DataFrame({
        "double_top": pd.Series([100, 120, 112, 119, 116, 110], index=range(1, 7)),
        "head_shoulders": pd.Series([100, 115, 108, 125, 108, 117, 106], index=range(1, 8)),
        "triangle": pd.Series([100, 110, 104, 110, 107, 110, 113], index=range(1, 8)),
        "wedge": pd.Series([100, 110, 106, 114, 112, 116, 110], index=range(1, 8)),
    }, dtype=float)
    return {"structure": pd.DataFrame({"close": structure}), "breakout": breakout,
            "position": position, "momentum": momentum_frame, "bands": bands, "profile": profile,
            "breakout_paths": branches, "patterns": patterns, **multi_timeframe_data()}


def readings(data: dict[str, pd.DataFrame]) -> dict:
    position, momentum, profile = data["position"], data["momentum"], data["profile"]
    selected = profile.loc[profile.value_area]
    return {
        "position_last": {key: float(position.iloc[-1][key]) for key in
                          ("close", "sma20", "ema20", "sma60", "atr14", "distance_atr")},
        "sma60_change": float(position.sma60.iloc[-1] - position.sma60.iloc[-2]),
        "rebound_atr": float((116 - 114.8) / position.atr14.iloc[-1]),
        "momentum": {str(day): {key: float(momentum.loc[day, key]) for key in
                                ("close", "dif", "dea", "histogram", "rsi14")} for day in (100, 149, 155)},
        "profile": {"total": int(profile.volume.sum()), "value_volume": int(selected.volume.sum()),
                    "val": int(selected.lower.min()), "vah": int(selected.upper.max())},
        "timeframes": {scale: {"periods": len(data[f"timeframe_{scale}"]),
                                "last_close": float(data[f"timeframe_{scale}"].close.iloc[-1]),
                                "last_low": float(data[f"timeframe_{scale}"].low.iloc[-1])}
                       for scale in ("hourly", "daily", "weekly")},
    }


def line(series: pd.Series, name: str, color: str, dash: str = "solid") -> go.Scatter:
    return go.Scatter(x=series.index.tolist(), y=series.tolist(), name=name,
                      line=dict(color=color, width=2, dash=dash),
                      hovertemplate=f"第 %{{x}} 期<br>{name}：%{{y:.2f}}<extra></extra>")


def style(fig: go.Figure, *, ytitle: str = "价格单位", xtitle: str = "交易期") -> go.Figure:
    fig.update_layout(font=dict(size=12), hovermode="x unified",
                      margin=dict(l=54, r=20, t=68, b=52),
                      legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom", font=dict(size=11)))
    fig.update_xaxes(title_text=xtitle, nticks=6, fixedrange=False)
    fig.update_yaxes(title_text=ytitle, nticks=6, fixedrange=False)
    return fig


def mark(fig: go.Figure, x: int, y: float, text: str, *, ay: int = -32, ax: int = 0) -> None:
    fig.add_annotation(x=x, y=y, text=text, showarrow=True, arrowhead=0, ax=ax, ay=ay,
                       font=dict(size=11, color=INK), bgcolor="rgba(255,255,255,0.9)", borderpad=2)


def timeframe_chart(bars: pd.DataFrame, xlabel: str) -> go.Figure:
    fig = go.Figure(go.Candlestick(x=bars.index.tolist(), open=bars.open.tolist(),
                                  high=bars.high.tolist(), low=bars.low.tolist(), close=bars.close.tolist(),
                                  increasing=dict(line=dict(color=BLUE), fillcolor="rgba(37,99,235,0.18)"),
                                  decreasing=dict(line=dict(color=INK), fillcolor=INK), name="OHLC"))
    style(fig, xtitle=xlabel)
    fig.update_layout(showlegend=False, margin=dict(t=30), xaxis_rangeslider_visible=False)
    return fig


def pattern_chart(patterns: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=2, horizontal_spacing=0.15, vertical_spacing=0.24,
                        subplot_titles=["双顶", "头肩顶", "上升三角形", "上升楔形"])
    cases = [
        ("double_top", [([2, 6], [112, 112])], [(2, 120, "顶"), (4, 119, "顶")], [97, 126]),
        ("head_shoulders", [([2, 7], [108, 108])],
         [(2, 115, "左肩"), (4, 125, "头"), (6, 117, "右肩")], [97, 133]),
        ("triangle", [([2, 6], [110, 110]), ([1, 3, 5, 6], [100, 104, 107, 108.5])], [], [97, 118]),
        ("wedge", [([2, 4, 6], [110, 114, 116]), ([1, 3, 5, 6], [100, 106, 112, 115])], [], [97, 122]),
    ]
    for index, (name, boundaries, labels, yrange) in enumerate(cases):
        row, col = index // 2 + 1, index % 2 + 1
        axis = "" if index == 0 else str(index + 1)
        series = patterns[name].dropna()
        for xs, ys in boundaries:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=MUTED, width=1, dash="dash"),
                                    hoverinfo="skip"), row=row, col=col)
        for part, color, dash, label in [(series.iloc[:-1], INK, "solid", "形成过程"),
                                         (series.iloc[-2:], BLUE, "dot", "后续示例")]:
            fig.add_trace(go.Scatter(x=part.index.tolist(), y=part.tolist(), mode="lines+markers",
                                    line=dict(color=color, width=2, dash=dash), marker=dict(size=4),
                                    hovertemplate=f"{label}<br>节点 %{{x}}：%{{y:.1f}}<extra></extra>"), row=row, col=col)
        for x, y, label in labels:
            fig.add_annotation(x=x, y=y, text=label, xref=f"x{axis}", yref=f"y{axis}",
                               showarrow=False, yshift=14, font=dict(size=11, color=INK))
        if index < 2:
            fig.add_annotation(x=1, y=112 if index == 0 else 108, text="颈线", xref=f"x{axis}", yref=f"y{axis}",
                               showarrow=False, xanchor="left", yshift=-12, font=dict(size=11, color=MUTED))
        fig.update_xaxes(range=[0.7, 7.5], showticklabels=False, showgrid=False, zeroline=False, row=row, col=col)
        fig.update_yaxes(range=yrange, nticks=3, zeroline=False, row=row, col=col)
    fig.update_layout(showlegend=False, hovermode="closest", margin=dict(l=35, r=8, t=35, b=20), font=dict(size=11))
    for annotation in fig.layout.annotations[:4]:
        annotation.font.size = 12
    return fig


def build_charts(data: dict[str, pd.DataFrame]) -> dict[str, go.Figure]:
    viz.setup_plotly()
    figures: dict[str, go.Figure] = {}

    fig = make_subplots(rows=1, cols=2, column_widths=[0.3, 0.7], horizontal_spacing=0.12)
    fig.add_trace(go.Candlestick(x=[1], open=[100], high=[110], low=[95], close=[104],
                                increasing=dict(line=dict(color=BLUE), fillcolor="rgba(37,99,235,0.18)"),
                                showlegend=False, name="同一根 K 线"), row=1, col=1)
    for values, name, color, dash in [([100, 95, 110, 104], "先低后高", BLUE, "solid"),
                                      ([100, 110, 95, 104], "先高后低", ORANGE, "dash")]:
        fig.add_trace(go.Scatter(x=[0, 1, 2, 3], y=values, name=name, mode="lines+markers",
                                line=dict(color=color, width=2, dash=dash)), row=1, col=2)
    style(fig, xtitle="")
    fig.update_xaxes(rangeslider_visible=False, tickvals=[1], ticktext=["OHLC"], range=[0.4, 1.6], row=1, col=1)
    fig.update_xaxes(tickvals=[0, 1, 2, 3], ticktext=["开盘", "途中", "途中", "收盘"], row=1, col=2)
    fig.update_yaxes(range=[92, 113], tickvals=[95, 100, 104, 110])
    fig.update_yaxes(title_text="", showticklabels=False, row=1, col=2)
    figures["candle-paths"] = fig

    fig = style(go.Figure(line(data["structure"].close, "价格", INK)))
    fig.add_hline(y=119, line_dash="dot", line_color=MUTED)
    for x, text, ay in [(6, "110", -24), (9, "104", 28), (15, "118", -24), (19, "111", 28),
                         (25, "125", -24), (29, "119", 28), (34, "128", -24), (41, "116", 28),
                         (46, "122", -24), (51, "112", 28)]:
        mark(fig, x, float(data["structure"].loc[x, "close"]), text, ay=ay)
    fig.update_layout(showlegend=False)
    fig.update_yaxes(range=[96, 134])
    figures["market-structure"] = fig

    b = data["breakout"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=b.index.tolist(), open=b.open.tolist(), high=b.high.tolist(),
                                low=b.low.tolist(), close=b.close.tolist(), name="日 K",
                                increasing=dict(line=dict(color=BLUE), fillcolor="rgba(37,99,235,0.10)"),
                                decreasing=dict(line=dict(color=INK), fillcolor=INK)), row=1, col=1)
    fig.add_trace(go.Bar(x=b.index.tolist(), y=b.volume.tolist(), name="成交量",
                         marker=dict(color=[GOLD if x == 21 else "#CBD5E1" for x in b.index],
                                     line=dict(color=INK, width=0.5))), row=2, col=1)
    fig.add_hrect(y0=109, y1=111, fillcolor="rgba(212,160,23,0.12)", line_width=0, row=1, col=1)
    for boundary in (100, 110):
        fig.add_hline(y=boundary, line_dash="dot", line_color=MUTED, row=1, col=1)
    style(fig)
    fig.update_layout(showlegend=False, margin=dict(t=25))
    fig.update_xaxes(rangeslider_visible=False, title_text="", row=1, col=1)
    fig.update_yaxes(title_text="份", rangemode="tozero", row=2, col=1)
    fig.update_yaxes(range=[98, 120], row=1, col=1)
    figures["breakout-retest"] = fig

    p = data["position"]
    fig = go.Figure()
    for col, name, color, dash in [("close", "收盘价", INK, "solid"), ("sma20", "SMA20", BLUE, "solid"),
                                    ("ema20", "EMA20", ORANGE, "dot"), ("sma60", "SMA60", GOLD, "dash")]:
        fig.add_trace(line(p[col].loc[70:], name, color, dash))
    style(fig)
    figures["moving-averages"] = fig

    profile = data["profile"]
    fig = go.Figure(go.Bar(y=profile.price.tolist(), x=profile.volume.tolist(), orientation="h",
                          width=1.65, marker=dict(color=[BLUE if val else "#E2E8F0" for val in profile.value_area],
                                                 line=dict(color=INK, width=0.5)),
                          customdata=profile[["lower", "upper"]].values.tolist(),
                          hovertemplate="价格档 %{customdata[0]}—%{customdata[1]}<br>%{x} 份<extra></extra>"))
    style(fig, xtitle="成交量（份）")
    fig.update_xaxes(range=[0, 2100])
    fig.update_yaxes(tickvals=[100, 110, 115, 124, 130], range=[99, 131])
    fig.add_annotation(x=1700, y=115, text="POC", ax=28, ay=0, showarrow=True, arrowhead=0)
    for boundary in (110, 124):
        fig.add_hline(y=boundary, line_dash="dot", line_color=MUTED)
    fig.update_layout(showlegend=False, margin=dict(t=24))
    figures["volume-profile"] = fig

    bands = data["bands"]
    fig = go.Figure()
    for col, name, color, dash in [("upper", "上轨", MUTED, "dot"), ("lower", "下轨", MUTED, "dot"),
                                    ("middle", "SMA20", BLUE, "dash"), ("close", "收盘价", INK, "solid")]:
        fig.add_trace(line(bands[col], name, color, dash))
    style(fig)
    figures["bollinger-bands"] = fig

    fig = style(go.Figure(line(p.close.loc[70:], "收盘价", INK)))
    # The high at 130 becomes a confirmed local high after two lower closes.
    confirmed = 132
    for low, name, color, dash in [(100, "100→140", BLUE, "solid"), (110, "110→140", ORANGE, "dash")]:
        for ratio in (0.5, 0.618, 0.786):
            price = 140 - ratio * (140 - low)
            fig.add_trace(go.Scatter(x=[confirmed, 156], y=[price, price], name=name, mode="lines",
                                    legendgroup=name, showlegend=ratio == 0.618,
                                    line=dict(color=color, width=1, dash=dash),
                                    hovertemplate=f"{name} 回撤 {ratio:.1%}<br>{price:.2f}<extra></extra>"))
    fig.add_vline(x=confirmed, line_dash="dot", line_color=MUTED, line_width=1)
    mark(fig, confirmed, 144, "132 期确认", ax=-36, ay=-15)
    for x, label, ay in [(80, "100", 28), (110, "110", 28), (130, "140", -26), (150, "116", -28)]:
        mark(fig, x, float(p.loc[x, "close"]), label, ay=ay)
    fig.update_yaxes(range=[90, 150])
    fig.update_xaxes(range=[68, 160])
    figures["fibonacci-anchors"] = fig

    m = data["momentum"]
    fig = go.Figure()
    for col, name, color, dash in [("close", "收盘价", INK, "solid"), ("ema12", "EMA12", BLUE, "solid"),
                                    ("ema26", "EMA26", GOLD, "dash")]:
        fig.add_trace(line(m[col].loc[70:], name, color, dash))
    style(fig)
    mark(fig, 100, 120, "A · 120")
    mark(fig, 110, 112, "112", ay=28)
    mark(fig, 149, 125.5, "B · 125.5", ax=-20)
    fig.update_xaxes(range=[68, 158])
    fig.update_yaxes(range=[97, 130])
    figures["momentum-price"] = fig

    fig = go.Figure()
    shown = m.loc[70:]
    fig.add_trace(go.Bar(x=shown.index.tolist(), y=shown.histogram.tolist(), name="DIF−DEA",
                         marker=dict(color=[BLUE if val >= 0 else "#E2E8F0" for val in shown.histogram],
                                     line=dict(color=INK, width=0.5))))
    fig.add_trace(line(shown.dif, "DIF", BLUE))
    fig.add_trace(line(shown.dea, "DEA", GOLD, "dash"))
    style(fig, ytitle="价格单位")
    fig.add_hline(y=0, line_color=MUTED, line_width=1)
    for x, label in [(100, "A"), (149, "B")]:
        mark(fig, x, float(m.loc[x, "dif"]), f"{label} · {m.loc[x, 'dif']:.2f}", ax=-12)
    fig.update_xaxes(range=[68, 158])
    figures["momentum-macd"] = fig

    fig = style(go.Figure(line(shown.rsi14, "RSI14", BLUE)), ytitle="RSI")
    for level in (30, 50, 70):
        fig.add_hline(y=level, line_color=MUTED, line_dash="solid" if level == 50 else "dot", line_width=1)
    for x, label in [(100, "A"), (149, "B")]:
        mark(fig, x, float(m.loc[x, "rsi14"]), f"{label} · {m.loc[x, 'rsi14']:.1f}", ay=28, ax=-12)
    fig.update_yaxes(range=[0, 100], tickvals=[0, 30, 50, 70, 100])
    fig.update_xaxes(range=[68, 158])
    fig.update_layout(showlegend=False, margin=dict(t=24))
    figures["momentum-rsi"] = fig

    branches = data["breakout_paths"]
    fig = go.Figure()
    for column, name, color, dash in [("history", "共同历史", INK, "solid"),
                                     ("path_a", "情景 A", BLUE, "dash"),
                                     ("path_b", "情景 B", ORANGE, "dot")]:
        fig.add_trace(line(branches[column].dropna(), name, color, dash))
    style(fig, xtitle="教学交易日")
    fig.add_hrect(y0=109, y1=111, fillcolor=GOLD, opacity=0.12, line_width=0, layer="below")
    fig.add_hline(y=100, line_dash="dot", line_color=MUTED)
    fig.add_vline(x=21, line_dash="dot", line_color=MUTED)
    for x, y, label, ay in [(21, 112, "共同起点", -28), (24, 110.6, "110.6", 28),
                            (27, 116, "A · 116", -28), (27, 104, "B · 104", 28)]:
        mark(fig, x, y, label, ay=ay, ax=-12)
    fig.update_xaxes(range=[0, 29])
    fig.update_yaxes(range=[97, 120])
    figures["breakout-paths"] = fig
    figures["pattern-comparison"] = pattern_chart(data["patterns"])

    weekly = data["timeframe_weekly"]
    fig = timeframe_chart(weekly, "教学周")
    fig.add_hrect(y0=118, y1=122, fillcolor=ORANGE, opacity=0.1, line_width=0, layer="below")
    fig.add_vrect(x0=33.5, x1=42.5, fillcolor=BLUE, opacity=0.05, line_width=0, layer="below")
    for x, y, ay in [(3, 160, -22), (9, 120, 24), (14, 140, -22), (21, 100, 24),
                      (27, 120, -22), (34, 80, 24), (42, 112, -28)]:
        mark(fig, x, y, str(y), ay=ay, ax=-12 if x == 42 else 0)
    fig.update_yaxes(range=[68, 173])
    fig.update_xaxes(range=[0, 45])
    figures["timeframe-weekly"] = fig

    daily = data["timeframe_daily"].loc[168:]
    fig = timeframe_chart(daily, "教学交易日")
    for lo, hi, color in [(118, 122, ORANGE), (109, 111, GOLD), (102, 104, BLUE)]:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=color, opacity=0.1, line_width=0, layer="below")
    for x, y, ay in [(170, 80, 24), (176, 92, -22), (180, 86, 24), (186, 100, -22),
                      (190, 94, 24), (196, 110, -22), (200, 103, 30), (206, 112, -28), (210, 108, 28)]:
        mark(fig, x, y, str(y), ay=ay)
    fig.update_xaxes(range=[166, 213])
    fig.update_yaxes(range=[73, 125])
    figures["timeframe-daily"] = fig

    hourly = data["timeframe_hourly"].loc[821:].copy()
    hourly.index = np.arange(1, 21)
    fig = timeframe_chart(hourly, "最近 20 个教学交易小时")
    fig.add_trace(line(hourly.close, "小时收盘价", BLUE, "dot"))
    fig.add_hline(y=109.5, line_dash="dash", line_color=MUTED)
    for x, y, ay in [(4, 112, -25), (9, 111, -25), (13, 109.5, -28), (17, 108.8, -25),
                      (7, 109.4, 26), (11, 108.5, 26), (15, 107.5, 26), (19, 106.8, 26), (20, 108, -10)]:
        mark(fig, x, y, str(y), ay=ay, ax=18 if x == 20 else 0)
    fig.update_xaxes(range=[0, 23], tickvals=[4, 8, 12, 16, 20])
    fig.update_yaxes(range=[105.6, 113.5])
    figures["timeframe-hourly"] = fig
    return figures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-data", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    data = teaching_data()
    summary = readings(data)
    if args.summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.export_data:
        target = ROOT / "data" / "technical-analysis"
        target.mkdir(exist_ok=True, parents=True)
        for name, frame in data.items():
            frame.to_csv(target / f"{name}.csv", index_label="row" if name == "profile" else "period",
                         float_format="%.10f", lineterminator="\n")
        (target / "readings.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not (args.summary or args.export_data):
        writer = ReportWriter()
        for name, figure in build_charts(data).items():
            writer.write_plotly(figure, name)
        writer.finish()


if __name__ == "__main__":
    main()
