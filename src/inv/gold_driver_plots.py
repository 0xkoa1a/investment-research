"""Question-specific Phase 2 figures; all inputs supplied by the offline loader."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from inv.gold_analysis import AS_OF, BASELINE

GOLD, BLUE, TEAL, GRAY = '#A87806', '#2563EB', '#0F766E', '#64748B'


def panels(top: str, bottom: str) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.26)
    fig.update_layout(
        template='plotly_white', margin=dict(l=57, r=15, t=55, b=35),
        font=dict(family='Arial, PingFang SC, sans-serif', size=11),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode='closest',
        legend=dict(orientation='h', x=0, y=1.16, yanchor='top', font=dict(size=10)),
        legend2=dict(orientation='h', x=0, y=.51, yanchor='top', font=dict(size=10)),
    )
    fig.update_xaxes(type='date', range=[BASELINE, '2026-09-09'], tickformat='%m/%d', nticks=5,
                     showgrid=False, zeroline=False)
    fig.update_yaxes(title_text=top, nticks=4, row=1, col=1)
    fig.update_yaxes(title_text=bottom, nticks=4, row=2, col=1)
    for row in [1, 2]:
        fig.add_vline(x='2026-08-25', line_width=1, line_dash='dot', line_color='#94A3B8',
                      row=row, col=1, exclude_empty_subplots=False)
    return fig


def line(fig: go.Figure, series: pd.Series, name: str, color: str, row: int, *,
         unit: str, dash: str = 'solid') -> None:
    series = series.loc[BASELINE:AS_OF]
    # Insert empty weekdays, including source-lag tails; never extend the last known value.
    series = series.reindex(series.index.union(pd.bdate_range(BASELINE, AS_OF))).sort_index()
    fig.add_trace(go.Scatter(
        x=series.index.strftime('%Y-%m-%d').tolist(),
        y=[None if pd.isna(v) else float(v) for v in series],
        name=name, legend='legend' if row == 1 else 'legend2', mode='lines+markers', connectgaps=False,
        line=dict(color=color, width=2, dash=dash), marker=dict(size=4),
        hovertemplate=f'%{{x|%Y-%m-%d}}<br>{name}：%{{y:,.2f}} {unit}<extra></extra>'), row=row, col=1)


def annotate_gold_events(fig: go.Figure, events: list[dict], evidence: dict) -> None:
    """Mark exact releases separately from whole-day context, using saved evidence."""
    jobs = next(event for event in events if event['id'] == 'E1')
    selected = [
        ('就业', jobs['released_at'], '七月就业报告'),
        ('纪要', evidence['sources']['minutes']['released_at'], '七月FOMC纪要'),
        ('讲话', evidence['sources']['warsh_speech']['released_at'], '沃什讲话'),
    ]
    times = [pd.Timestamp(released_at).tz_convert('America/New_York').tz_localize(None).isoformat()
             for _, released_at, _ in selected]
    for released_at in times:
        fig.add_shape(type='line', x0=released_at, x1=released_at, y0=0, y1=.90,
                      xref='x', yref='paper', line=dict(color='#C2CCD7', width=1, dash='dot'), layer='below')
    fig.add_trace(go.Scatter(
        x=times, y=[.90] * len(selected), yaxis='y2',
        mode='markers+text', text=[label for label, _, _ in selected], textposition='top center',
        marker=dict(symbol='diamond', size=9, color=BLUE), name='发布时间',
        customdata=[detail for _, _, detail in selected],
        hovertemplate='%{customdata}<br>发布：%{x|%m/%d %H:%M} 纽约<extra></extra>',
    ))
    conflict = next(case for case in evidence['cases'] if case['id'] == 'aug31')
    for date, label in [(evidence['sources']['buybacks']['published_date'], '财政部消息'),
                        (conflict['date'], '冲突后<br>首个交易日')]:
        start = pd.Timestamp(date)
        fig.add_vrect(x0=start.isoformat(), x1=(start + pd.Timedelta(days=1)).isoformat(),
                      fillcolor='#64748B', opacity=.10, line_width=0, layer='below')
        # Midday centers a whole-day label; it is not an assumed announcement timestamp.
        fig.add_annotation(x=(start + pd.Timedelta(hours=12)).isoformat(), y=.84, yref='paper',
                           text=label, showarrow=False, yanchor='top',
                           font=dict(size=10, color='#475569'))


def write_driver_plots(writer, frames: dict, gold: pd.Series) -> None:
    fig = panels('金价 · 美元/盎司', '九月加息概率 · %')
    daily_gold = gold.tz_convert('America/New_York').between_time('17:00', '17:00').copy()
    daily_gold.index = daily_gold.index.tz_localize(None).normalize()
    line(fig, daily_gold, '黄金', GOLD, 1, unit='美元/金衡盎司')
    # User-selected inverse rate axis: falling yields plot upward; values retain their original signs.
    fig.update_layout(
        margin=dict(r=55), hovermode='x unified', hoverlabel=dict(font_size=10),
        legend=dict(entrywidth=60, entrywidthmode='pixels'),
        yaxis3=dict(overlaying='y', anchor='x', side='right', title='利率 · 基点（反向）',
                    autorange='reversed', nticks=4, showgrid=False, zeroline=False),
    )
    fig.update_yaxes(tickformat=',.0f', row=1, col=1)
    for name, label, color, dash in [('real10y', '10年实际', BLUE, 'dash'),
                                    ('ust2y', '2年名义', '#94A3B8', 'solid')]:
        s = frames[name].value
        line(fig, (s - s.loc[BASELINE]) * 100, label, color, 1, unit='bp', dash=dash)
        fig.data[-1].update(yaxis='y3', visible=True if name == 'real10y' else 'legendonly')
    line(fig, frames['fedwatch_20260916'].higher_pct, '9/16会议后', BLUE, 2, unit='%')
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    writer.write_plotly(fig, 'rates-policy')

    fig = panels('7/31 = 100', 'WTI · 美元/桶')
    for name, label, color, dash in [('dxy', 'DXY', BLUE, 'solid'),
                                    ('usd_broad', '广义美元', TEAL, 'dash')]:
        s = frames[name].value
        line(fig, s / s.loc[BASELINE] * 100, label, color, 1, unit='指数', dash=dash)
    for name, label, color, dash in [('wti', 'WTI现货', GOLD, 'solid'),
                                    ('wti_futures', 'CL=F期货', GRAY, 'dash')]:
        line(fig, frames[name].value, label, color, 2, unit='美元/桶', dash=dash)
    writer.write_plotly(fig, 'dollar-energy')

    fig = panels('GLD持金量 · 吨', '周度净额变化 · 万手')
    line(fig, frames['gld_holdings'].tonnes, 'GLD持金量', GOLD, 1, unit='吨')
    cot = frames['cot'].loc['2026-08-04':AS_OF]
    releases = pd.to_datetime(cot.available_at, utc=True).dt.tz_convert('America/New_York')
    for key, label, color in [('long_change', '多头增减', BLUE),
                              ('short_contribution', '空头减少/增加', TEAL)]:
        fig.add_trace(go.Bar(
            x=cot.index.strftime('%Y-%m-%d').tolist(), y=(cot[key] / 10000).tolist(),
            name=label, legend='legend2', marker_color=color,
            customdata=[[str(released), float(amount), f'{amount:+,.0f}']
                        for released, amount in zip(releases, cot[key], strict=True)],
            hovertemplate=f'持仓日：%{{x|%m/%d}}<br>{label}：%{{customdata[2]}} 手'
                          '<br>公布：%{customdata[0]}<extra></extra>'), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=cot.index.strftime('%Y-%m-%d').tolist(), y=(cot.net_change / 10000).tolist(),
        mode='markers', marker=dict(symbol='diamond', size=7, color='#334155', line=dict(color='white', width=.7)),
        name='净额变化', legend='legend2',
        customdata=[f'{value / 10000:+.4f}' for value in cot.net_change],
        hovertemplate='持仓日：%{x|%m/%d}<br>净额变化：%{customdata} 万手<extra></extra>'), row=2, col=1)
    fig.update_layout(barmode='relative', bargap=.4)
    fig.update_xaxes(tickmode='array', tickvals=cot.index.strftime('%Y-%m-%d').tolist(), row=2, col=1)
    fig.update_yaxes(zeroline=True, zerolinecolor='#64748B', row=2, col=1)
    writer.write_plotly(fig, 'holdings-positioning')
