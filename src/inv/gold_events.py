"""Offline event windows on an explicit COMEX calendar and fixed five-minute bars."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from inv import config as C
from inv.gold_analysis import checked_series
from inv.gold_drivers import digest
from inv.gold_intraday import NY


def aware(value: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError('事件与截止时刻必须注明时区')
    return ts.tz_convert(NY)


def checked_calendar(dates) -> pd.DatetimeIndex:
    calendar = pd.DatetimeIndex(dates)
    if (not len(calendar) or calendar.tz is not None or calendar.has_duplicates
            or not calendar.is_monotonic_increasing or not calendar.equals(calendar.normalize())):
        raise ValueError('交易日期必须无时区、唯一、递增且不含日内时刻')
    return calendar


def close_at(date) -> pd.Timestamp:
    return pd.Timestamp(date).tz_localize(NY) + pd.Timedelta(hours=17)


def event_session(released_at: str, calendar: pd.DatetimeIndex) -> str:
    """A release at/after the endpoint cannot affect that already-ended bar."""
    release = aware(released_at)
    for date in checked_calendar(calendar):
        if close_at(date) > release:
            return date.date().isoformat()
    raise ValueError('事件超出已核验交易日历')


def point(prices: pd.Series, end: pd.Timestamp, cutoff: pd.Timestamp) -> dict:
    status = 'not_completed' if end > cutoff else 'observed' if end in prices.index else 'missing_price'
    return {'bar_end': end.isoformat(), 'close': float(prices.loc[end]) if status == 'observed' else None,
            'status': status}


def change(start, end):
    return None if start is None or end is None else float((end / start - 1) * 100)


def event_window(prices: pd.Series, date: str, calendar: pd.DatetimeIndex, cutoff: str) -> dict:
    prices = checked_series(prices)
    if prices.index.tz is None:
        raise ValueError('价格必须注明时区')
    calendar, cutoff = checked_calendar(calendar), aware(cutoff)
    position = calendar.get_loc(pd.Timestamp(date))
    if position == 0:
        raise ValueError('缺少事件前一交易日')
    previous = calendar[position - 1]
    baseline = {'date': previous.date().isoformat(), **point(prices, close_at(previous), cutoff)}
    windows = []
    for horizon in (0, 1, 3, 5):
        offset = position + horizon
        if offset >= len(calendar):
            windows.append({'horizon': horizon, 'date': None, 'bar_end': None, 'close': None,
                            'status': 'outside_calendar', 'change_pct': None})
            continue
        end = calendar[offset]
        item = {'horizon': horizon, 'date': end.date().isoformat(), **point(prices, close_at(end), cutoff)}
        item['change_pct'] = change(baseline['close'], item['close'])
        windows.append(item)
    return {'date': date, 'baseline': baseline, 'windows': windows}


def announcement_reaction(prices: pd.Series, released_at: str, cutoff: str) -> dict:
    prices = checked_series(prices)
    if prices.index.tz is None:
        raise ValueError('价格必须注明时区')
    release, cutoff = aware(released_at), aware(cutoff)
    if release.second or release.minute % 5:
        raise ValueError('本复盘仅处理位于五分钟边界的公告')
    if release > cutoff:
        raise ValueError('事件晚于行情截止')
    # Release-boundary bar may contain no reaction; use the preceding completed bar.
    before = point(prices, release - pd.Timedelta(minutes=5), cutoff)
    after = []
    for minutes in (5, 30, 60):
        item = {'minutes_after_release': minutes,
                **point(prices, release + pd.Timedelta(minutes=minutes), cutoff)}
        item['change_from_before_pct'] = change(before['close'], item['close'])
        after.append(item)
    end = close_at(release.tz_localize(None).normalize())
    final = point(prices, end, cutoff)
    final['change_from_before_pct'] = change(before['close'], final['close'])
    return {'released_at': release.isoformat(), 'before': before, 'after': after, 'day_close': final}


def driver_change(series: pd.Series, start: str, end: str, unit: str) -> dict:
    def value(date):
        v = series.get(pd.Timestamp(date))
        return None if pd.isna(v) else float(v)
    first, last = value(start), value(end)
    delta = None
    if first is not None and last is not None:
        delta = change(first, last) if unit == 'percent' else (last - first) * (100 if unit == 'bp' else 1)
    return {'start_date': start, 'end_date': end, 'start': first, 'end': last, 'change': delta,
            'unit': unit, 'status': 'observed' if delta is not None else 'missing_endpoint'}


def load_event_evidence(root: Path = C.ROOT) -> tuple[dict, dict]:
    path = root / 'data/raw/gold-outlook/phase3'
    selection = json.loads((path / 'inputs.json').read_text())
    for relative, expected in selection['files'].items():
        source = (root / relative).resolve()
        if not source.is_relative_to((root / 'data/raw/gold-outlook').resolve()) or digest(source) != expected:
            raise ValueError(f'事件输入哈希不符：{relative}')
    evidence = json.loads((path / 'evidence.json').read_text())
    cutoff = aware(selection['information_cutoff_at'])
    for case in evidence['cases']:
        if case['released_at'] and aware(case['released_at']) > cutoff:
            raise ValueError('事件信息晚于基准截止')
    if evidence['information_cutoff_at'] != selection['information_cutoff_at']:
        raise ValueError('事件信息截止不一致')
    return evidence, {'selection_sha256': digest(path / 'inputs.json'), **selection}


def event_statistics(prices: pd.Series, frames: dict, evidence: dict, provenance: dict) -> dict:
    calendar = checked_calendar(evidence['calendar']['dates'])
    cutoff = provenance['sample_end']
    cases = []
    for case in evidence['cases']:
        if case['released_at'] and event_session(case['released_at'], calendar) != case['date']:
            raise ValueError('事件日期与发布时间对应的交易日不一致')
        window = event_window(prices, case['date'], calendar, cutoff)
        daily = {}
        for name, column, unit in [('ust2y', 'value', 'bp'), ('real10y', 'value', 'bp'),
                                   ('dxy', 'value', 'percent'), ('wti_futures', 'value', 'percent'),
                                   ('fedwatch_20260916', 'higher_pct', 'percentage_points')]:
            daily[name] = [dict(horizon=w['horizon'], **driver_change(
                frames[name][column], window['baseline']['date'], w['date'], unit))
                for w in window['windows'] if w['date'] is not None]
        result = {'id': case['id'], 'label': case['label'], **window, 'drivers': daily}
        if case['released_at']:
            reaction = announcement_reaction(prices, case['released_at'], cutoff)
            reaction['before']['change_from_previous_close_pct'] = change(
                window['baseline']['close'], reaction['before']['close'])
            start = aware(case['released_at']).normalize() + pd.Timedelta(hours=8)
            expected = pd.date_range(start, close_at(pd.Timestamp(case['date'])), freq='5min')
            reaction['chart_missing_bar_ends'] = [v.isoformat() for v in expected.difference(prices.index)]
            result['intraday'] = reaction
        cases.append(result)
    sunday = prices.loc[aware('2026-08-30T18:00:00-04:00'):aware('2026-08-30T19:00:00-04:00')]
    weekend = None
    if len(sunday):
        weekend = {'first_observed_bar_end': sunday.index[0].tz_convert(NY).isoformat(),
                   'first_observed_close': float(sunday.iloc[0]),
                   'change_from_friday_close_pct': change(cases[-1]['baseline']['close'], float(sunday.iloc[0])),
                   'not_opening_quote': True}
    return {'phase': 3, 'inputs': provenance, 'cases': cases, 'weekend': weekend,
            'method': 'Cumulative return from prior session 17:00 Close; no filling or calendar shifts for missing prices. '
                      'Drivers retain their source dates; multi-day windows include later news.'}


def write_event_plot(writer, prices: pd.Series, statistics: dict) -> None:
    fig = make_subplots(rows=2, cols=1, vertical_spacing=.25)
    limits = []
    for row, case in enumerate([c for c in statistics['cases'] if 'intraday' in c], 1):
        start = aware(case['intraday']['released_at']).normalize() + pd.Timedelta(hours=8)
        end = close_at(pd.Timestamp(case['date']))
        grid = pd.date_range(start, end, freq='5min')
        actual = prices.reindex(grid)
        relative = (actual / case['baseline']['close'] - 1) * 100
        limits.extend(relative.dropna().tolist())
        fig.add_trace(go.Scatter(
            x=grid.tz_localize(None).strftime('%Y-%m-%dT%H:%M:%S').tolist(),
            y=[None if pd.isna(v) else float(v) for v in relative],
            customdata=[None if pd.isna(v) else float(v) for v in actual],
            mode='lines', connectgaps=False, line=dict(color='#A87806', width=2),
            hovertemplate='%{x|%m/%d %H:%M} 纽约<br>黄金：%{customdata:,.2f} 美元/盎司'
                          '<br>较前日17:00：%{y:.2f}%<extra></extra>'), row=row, col=1)
        release = aware(case['intraday']['released_at']).tz_localize(None).isoformat()
        fig.add_vline(x=release, line=dict(color='#2563EB', width=1.5, dash='dash'), row=row, col=1)
        fig.add_hline(y=0, line_color='#94A3B8', line_width=1, row=row, col=1)
        label = '8/19 · 纪要14:00公布' if row == 1 else '8/28 · 讲话10:00开始'
        fig.add_annotation(text=label, x=0, y=1.05 if row == 1 else .425,
                           xref='paper', yref='paper', showarrow=False, xanchor='left',
                           font=dict(size=12, color='#334155'))
        fig.update_xaxes(range=[start.tz_localize(None).isoformat(), end.tz_localize(None).isoformat()],
                         dtick=10800000, tick0=start.tz_localize(None).isoformat(),
                         tickformat='%H:%M', type='date', showgrid=False, row=row, col=1)
    fig.update_layout(template='plotly_white', margin=dict(l=48, r=14, t=30, b=35),
                      font=dict(family='Arial, PingFang SC, sans-serif', size=11), showlegend=False,
                      hovermode='closest', hoverlabel=dict(font_size=11),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    fig.update_yaxes(title='涨跌 · %', ticksuffix='%', range=[min(limits) - .35, max(limits) + .35],
                      dtick=2, zeroline=False)
    writer.write_plotly(fig, 'event-intraday')
