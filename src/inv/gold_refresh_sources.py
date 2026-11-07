"""Download and validate Yahoo Chart API observations for gold research."""
from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from curl_cffi import requests

FIELDS = ['open', 'high', 'low', 'close', 'volume']
NY = ZoneInfo('America/New_York')
ALLOWED = {
    'GCZ26.CMX': {'instrumentType': 'FUTURE'}, 'GCV26.CMX': {'instrumentType': 'FUTURE'},
    'GC=F': {'instrumentType': 'FUTURE'}, 'DX-Y.NYB': {}, 'CL=F': {}, 'GLD': {},
}


def _aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{label} 必须是带时区的 datetime')
    return value


def _metadata(payload: dict, symbol: str, interval: str, start: datetime, cutoff: datetime) -> dict:
    try:
        result = payload['chart']['result'][0]
        meta = result['meta']
        actual_symbol = meta['symbol']
        currency = meta['currency']
        instrument = meta['instrumentType']
        timezone = meta['exchangeTimezoneName']
        granularity = meta['dataGranularity']
        timestamps = result['timestamp']
        quote_data = result['indicators']['quote'][0]
    except (KeyError, IndexError, TypeError) as exc:
        error = payload.get('chart', {}).get('error') if isinstance(payload, dict) else None
        raise ValueError(f'Yahoo Chart 响应结构错误: {error or exc}') from exc
    if actual_symbol != symbol:
        raise ValueError(f'Yahoo 返回品种 {actual_symbol!r} 与请求 {symbol!r} 不符')
    if currency != 'USD':
        raise ValueError(f'{symbol} 计价单位不是 USD: {currency!r}')
    expected = ALLOWED.get(symbol)
    if expected is None or (expected.get('instrumentType') and instrument != expected['instrumentType']):
        raise ValueError(f'{symbol} 品种类型不符合允许范围: {instrument!r}')
    if granularity != interval:
        raise ValueError(f'{symbol} 返回频率 {granularity!r} 与请求 {interval!r} 不符')
    try:
        ZoneInfo(timezone)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Yahoo 返回无效交易所时区: {timezone!r}') from exc
    if not isinstance(timestamps, list) or not timestamps:
        raise ValueError(f'{symbol} 返回空行情序列')
    if any(len(quote_data.get(field, [])) != len(timestamps) for field in FIELDS):
        raise ValueError(f'{symbol} OHLCV 序列长度不一致')
    url = f'https://finance.yahoo.com/quote/{quote(symbol, safe="")}/history/'
    return {
        'source': 'Yahoo Chart API', 'symbol': actual_symbol, 'currency': currency,
        'instrumentType': instrument, 'exchangeTimezoneName': timezone,
        'dataGranularity': granularity, 'retrieved_at': datetime.now().astimezone().isoformat(),
        'request_start': start.isoformat(), 'request_end': cutoff.isoformat(), 'source_url': url,
        'timestamp_semantics': 'Yahoo 5m timestamps are treated as bar starts' if interval == '5m' else 'exchange-local calendar date',
        'raw_response': payload,
    }, result, timestamps, quote_data


def normalize_yahoo_response(payload: dict, symbol: str, interval: str, start: datetime,
                             cutoff: datetime) -> tuple[pd.DataFrame, dict]:
    start, cutoff = _aware(start, 'start'), _aware(cutoff, 'cutoff')
    if start >= cutoff:
        raise ValueError('请求起止时间顺序错误')
    if interval not in {'1d', '5m'}:
        raise ValueError(f'不支持的 Yahoo interval: {interval}')
    if interval == '5m' and cutoff.astimezone(ZoneInfo('UTC')) - start.astimezone(ZoneInfo('UTC')) > timedelta(days=60):
        raise ValueError('Yahoo 5m 请求跨度不能超过最近 60 天')
    meta, result, timestamps, values = _metadata(payload, symbol, interval, start, cutoff)
    index = pd.to_datetime(timestamps, unit='s', utc=True)
    frame = pd.DataFrame({field: values[field] for field in FIELDS})
    try:
        frame = frame.apply(pd.to_numeric, errors='raise')
    except (TypeError, ValueError) as exc:
        raise ValueError('Yahoo OHLCV 包含非数值字段') from exc
    if index.has_duplicates:
        raise ValueError('Yahoo 行情存在重复时间')
    if not index.is_monotonic_increasing:
        raise ValueError('Yahoo 行情时间未递增')
    frame.index = index
    if np.isinf(frame.to_numpy(dtype=float)).any():
        raise ValueError('Yahoo 行情包含无穷值')
    prices = frame[['open', 'high', 'low', 'close']]
    full = prices.notna().all(axis=1)
    if ((prices <= 0) & prices.notna()).any().any() or (frame.volume < 0).any():
        raise ValueError('Yahoo 价格或成交量非法')
    if ((frame.high < prices[['open', 'close', 'low']].max(axis=1)) & full).any() or (
        (frame.low > prices[['open', 'close', 'high']].min(axis=1)) & full
    ).any():
        raise ValueError('Yahoo OHLC 高低关系不一致')
    excluded = []
    if interval == '1d':
        local_date = index.tz_convert(meta['exchangeTimezoneName']).date
        if pd.Index(local_date).has_duplicates:
            raise ValueError('Yahoo 行情存在重复日期')
        lower_date = start.astimezone(ZoneInfo(meta['exchangeTimezoneName'])).date()
        boundary = cutoff.astimezone(NY).date()
        keep = np.array([lower_date <= d < boundary for d in local_date])
        for pos in np.flatnonzero(~keep):
            reason = 'before_request_start_exchange_date' if local_date[pos] < lower_date else 'cutoff_ny_calendar_day_or_later'
            excluded.append({'timestamp': index[pos].isoformat(), 'reason': reason})
        frame = frame.loc[keep].copy()
        frame.insert(0, 'date', [d.isoformat() for d, ok in zip(local_date, keep, strict=True) if ok])
    else:
        ends = index + pd.Timedelta(minutes=5)
        lower = pd.Timestamp(start).tz_convert('UTC')
        keep = (ends <= pd.Timestamp(cutoff).tz_convert('UTC')) & (index >= lower)
        # Only a seconds-misaligned final live tick close to cutoff is removable.
        misaligned = index != index.floor('5min')
        near_tail = (index >= pd.Timestamp(cutoff).tz_convert('UTC') - pd.Timedelta(minutes=15))
        bad_grid = misaligned & ~(near_tail & (np.arange(len(index)) == len(index) - 1))
        if bad_grid.any():
            raise ValueError('Yahoo 历史五分钟标签未对齐网格')
        excluded_positions = set(np.flatnonzero(~keep).tolist()) | set(np.flatnonzero(misaligned).tolist())
        for pos in sorted(excluded_positions):
            reasons = []
            if index[pos] < lower:
                reasons.append('before_request_start')
            if misaligned[pos]:
                reasons.append('unaligned_live_tail')
            elif ends[pos] > pd.Timestamp(cutoff).tz_convert('UTC'):
                reasons.append('bar_not_completed_by_cutoff')
            excluded.append({'timestamp': index[pos].isoformat(), 'reason': reasons})
        keep &= ~misaligned
        frame = frame.loc[keep].copy()
        frame.insert(0, 'timestamp', [t.isoformat().replace('+00:00', 'Z') for t in frame.index])
    frame = frame.sort_values('date' if interval == '1d' else 'timestamp').reset_index(drop=True)
    if frame.empty:
        raise ValueError(f'{symbol} 没有截止时点前的完整 {interval} 行情')
    meta.update({'raw_rows': len(timestamps), 'retained_rows': len(frame), 'excluded': excluded,
                 'missing_close_rows': int(frame.close.isna().sum()),
                 'missing_ohlcv_rows': int(frame[FIELDS].isna().any(axis=1).sum())})
    return frame, meta


def fetch_yahoo(symbol: str, interval: str, start: datetime, cutoff: datetime) -> tuple[pd.DataFrame, dict]:
    start, cutoff = _aware(start, 'start'), _aware(cutoff, 'cutoff')
    params = {'period1': int(start.timestamp()), 'period2': int(cutoff.timestamp()), 'interval': interval,
              'events': 'history', 'includeAdjustedClose': 'false'}
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe="")}'
    try:
        response = requests.get(url, params=params, timeout=30, impersonate='chrome')
    except requests.exceptions.RequestException as exc:
        raise ValueError(f'Yahoo 请求失败: {type(exc).__name__}') from exc
    if response.status_code != 200:
        raise ValueError(f'Yahoo HTTP 状态异常: {response.status_code}')
    try:
        payload = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise ValueError('Yahoo 返回无效 JSON') from exc
    return normalize_yahoo_response(payload, symbol, interval, start, cutoff)
