"""Phases 1–4: immutable local inputs -> statistics and charts; never fetch data."""
from __future__ import annotations

import hashlib
import json
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go

from inv import config as C
from inv.gold_analysis import AS_OF, BASELINE, intraday_results, load_inputs, results
from inv.gold_data import timestamp
from inv.gold_driver_plots import annotate_gold_events, write_driver_plots
from inv.gold_drivers import driver_statistics, load_drivers, write_json
from inv.gold_events import event_statistics, load_event_evidence, write_event_plot
from inv.gold_intraday import broken_line, load_intraday
from inv.gold_update import load_update, update_statistics
from inv.reporting import ReportWriter

frames, provenance = load_inputs()
event_path = C.GOLD_RESEARCH_RAW / 'phase1/events.json'
evidence = json.loads(event_path.read_text())
events = evidence['events']
for event in events:
    if timestamp(event['released_at']) > timestamp(evidence['information_cutoff_at']):
        raise ValueError('事件晚于基准信息截止')
    if event['date'] != timestamp(event['released_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat():
        raise ValueError('事件日期与纽约发布时间不符')
provenance['events_sha256'] = hashlib.sha256(event_path.read_bytes()).hexdigest()
daily_summary = results(frames, provenance)
intraday, intraday_provenance = load_intraday()
summary = intraday_results(intraday, intraday_provenance)
summary['background'] = daily_summary['background']
summary['background_inputs'] = provenance
updated, update_provenance, update_evidence = load_update()
event_evidence, event_provenance = load_event_evidence()
summary['event_annotation_inputs'] = event_provenance
jobs = next(event for event in events if event['id'] == 'E1')
release = pd.Timestamp(jobs['released_at'])
before = release - pd.Timedelta(minutes=5)
day_end = release.normalize() + pd.Timedelta(hours=17)
baseline_price = float(intraday.loc[pd.Timestamp(summary['overall']['start'])])
before_price, day_end_price = float(intraday.loc[before]), float(intraday.loc[day_end])
summary['employment_timing'] = {
    'released_at': release.isoformat(),
    'before_bar_end': before.isoformat(), 'before_price': before_price,
    'day_end': day_end.isoformat(), 'day_end_price': day_end_price,
    'baseline_price': baseline_price,
    'before_return_pct': (before_price / baseline_price - 1) * 100,
    'day_end_return_pct': (day_end_price / baseline_price - 1) * 100,
    'after_return_pct': (day_end_price / before_price - 1) * 100,
}
update_as_of = update_provenance['sample_end'][:10]
writer = ReportWriter('gold-outlook', data_as_of=update_as_of)
GOLD, BLUE = '#B8860B', '#2563EB'


def figure(ytitle: str, *, history: bool = False) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white', margin=dict(l=58, r=20, t=25, b=45),
        font=dict(family='Arial, PingFang SC, sans-serif', size=12),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        hovermode='closest', showlegend=False,
        xaxis=dict(type='date', tickformat='%Y-%m' if history else '%m/%d', nticks=5 if history else 6,
                   title=None, showgrid=False, zeroline=False),
        yaxis=dict(title=ytitle, tickformat=',.0f' if '美元' in ytitle else '.1f', zeroline=False),
    )
    return fig


def trace(series: pd.Series, name: str, color: str, *, dash: str = 'solid', markers: bool = False) -> go.Scatter:
    return go.Scatter(x=series.index.strftime('%Y-%m-%d').tolist(), y=series.tolist(),
                      name=name, mode='lines+markers' if markers else 'lines', connectgaps=False,
                      line=dict(color=color, width=2, dash=dash), marker=dict(size=5),
                      hovertemplate=f'%{{x|%Y-%m-%d}}<br>{name}：%{{y:,.2f}}<extra></extra>')


primary = frames['gold']
fig = figure('美元/金衡盎司', history=True)
fig.add_trace(trace(primary, 'GC=F Close', GOLD))
fig.add_vrect(x0=BASELINE, x1=AS_OF, fillcolor=BLUE, opacity=.10, line_width=0)
fig.update_layout(showlegend=False)
writer.write_plotly(fig, 'history')

focus = intraday.loc[summary['overall']['start']:summary['overall']['end']]
fig = figure('美元/金衡盎司')
x, y = broken_line(focus)
fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='十二月合约 · 5分钟 Close',
                        connectgaps=False, line=dict(color=GOLD, width=1.5),
                        hovertemplate='%{x|%m/%d %H:%M} 纽约<br>十二月合约：%{y:,.2f}<extra></extra>'))
fig.add_trace(go.Scatter(
    x=[x[0], x[-1]], y=[float(focus.iloc[0]), float(focus.iloc[-1])], mode='markers',
    marker=dict(size=6, color=GOLD), customdata=['7月末基准', '样本末日'],
    hovertemplate='%{customdata}<br>%{x|%m/%d %H:%M} 纽约<br>十二月合约：%{y:,.2f}<extra></extra>'))
marker_level = float(focus.max()) + 70
annotate_gold_events(fig, events, event_evidence)
fig.update_layout(yaxis=dict(range=[float(focus.min()) - 40, marker_level + 55]),
                  yaxis2=dict(overlaying='y', range=[0, 1], visible=False, fixedrange=True),
                  xaxis=dict(title='纽约时间 · 5分钟区间结束', tickformatstops=[
                      dict(dtickrange=[None, 86400000], value='%m/%d<br>%H:%M'),
                      dict(dtickrange=[86400000, None], value='%m/%d')]))
writer.write_plotly(fig, 'since-august')
drivers, driver_provenance = load_drivers()
driver_summary = driver_statistics(drivers, intraday, driver_provenance)
write_driver_plots(writer, drivers, intraday)
event_summary = event_statistics(intraday, drivers, event_evidence, event_provenance)
write_event_plot(writer, intraday, event_summary)
manifest_path = writer.finish()
charts = json.loads(manifest_path.read_text())['charts']
summary['charts'] = [chart for chart in charts if chart['file'] in {'history.json', 'since-august.json'}]
driver_summary['charts'] = [chart for chart in charts if chart['file'] in {
    'rates-policy.json', 'dollar-energy.json', 'holdings-positioning.json'}]
event_summary['charts'] = [chart for chart in charts if chart['file'] == 'event-intraday.json']
write_json(C.GOLD_RESEARCH_RAW / 'phase3/statistics.json', event_summary)
write_json(C.GOLD_RESEARCH_RAW / 'phase4/statistics.json',
           update_statistics(updated, drivers, intraday, update_provenance, update_evidence))
write_json(C.GOLD_RESEARCH_RAW / 'phase2/statistics.json', driver_summary)
(C.GOLD_RESEARCH_RAW / 'phase1/statistics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'overall':summary['overall'], 'stages':summary['stages']}, ensure_ascii=False))
