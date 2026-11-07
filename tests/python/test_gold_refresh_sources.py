from datetime import datetime, timezone

import pandas as pd
import pytest

from inv.gold_refresh_sources import fetch_yahoo, normalize_yahoo_response


def payload(timestamps, *, symbol='GCZ26.CMX', currency='USD', instrument='FUTURE', granularity='5m',
            closes=None):
    size = len(timestamps)
    values = {'open': [2000.0] * size, 'high': [2010.0] * size, 'low': [1990.0] * size,
              'close': closes if closes is not None else [2005.0] * size, 'volume': [1] * size}
    return {'chart': {'result': [{'meta': {'symbol': symbol, 'currency': currency,
            'instrumentType': instrument, 'exchangeTimezoneName': 'America/Chicago',
            'dataGranularity': granularity}, 'timestamp': timestamps,
            'indicators': {'quote': [values]}}], 'error': None}}


def epoch(value):
    return int(pd.Timestamp(value).timestamp())


def test_daily_date_uses_exchange_timezone_and_excludes_cutoff_day():
    p = payload([epoch('2026-09-07T01:00:00Z'), epoch('2026-09-08T15:00:00Z')], granularity='1d')
    frame, meta = normalize_yahoo_response(p, 'GCZ26.CMX', '1d', datetime(2026, 9, 1, tzinfo=timezone.utc),
                                            datetime(2026, 9, 8, 12, tzinfo=timezone.utc))
    assert frame.date.tolist() == ['2026-09-06']
    assert meta['excluded'][0]['reason'] == 'cutoff_ny_calendar_day_or_later'


def test_five_minute_completion_and_unaligned_live_tail():
    stamps = [epoch('2026-09-08T14:00:00Z'), epoch('2026-09-08T14:05:00Z'), epoch('2026-09-08T14:09:37Z')]
    p = payload(stamps)
    frame, meta = normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                                            datetime(2026, 9, 8, 14, 20, tzinfo=timezone.utc))
    assert len(frame) == 2
    assert frame.timestamp.iloc[0] == '2026-09-08T14:00:00Z'
    assert meta['excluded'][0]['reason'] == ['unaligned_live_tail']


@pytest.mark.parametrize('change, message', [
    ({'symbol': 'GC=F'}, '与请求'), ({'currency': 'EUR'}, '不是 USD'),
    ({'instrument': 'INDEX'}, '品种类型'),
])
def test_rejects_wrong_symbol_currency_or_instrument(change, message):
    options = {'symbol': 'GCZ26.CMX', 'currency': 'USD', 'instrument': 'FUTURE'}
    options.update(change)
    p = payload([epoch('2026-09-08T14:00:00Z')], **options)
    with pytest.raises(ValueError, match=message):
        normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                                 datetime(2026, 9, 8, 15, tzinfo=timezone.utc))


def test_rejects_duplicate_timestamps_and_inconsistent_high_low():
    stamp = epoch('2026-09-08T14:00:00Z')
    p = payload([stamp, stamp])
    with pytest.raises(ValueError, match='重复时间'):
        normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                                 datetime(2026, 9, 8, 15, tzinfo=timezone.utc))
    p = payload([stamp])
    p['chart']['result'][0]['indicators']['quote'][0]['high'] = [1980]
    with pytest.raises(ValueError, match='高低关系'):
        normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                                 datetime(2026, 9, 8, 15, tzinfo=timezone.utc))


def test_rejects_duplicate_exchange_dates():
    p = payload([epoch('2026-09-07T14:00:00Z'), epoch('2026-09-07T20:00:00Z')], granularity='1d')
    with pytest.raises(ValueError, match='重复日期'):
        normalize_yahoo_response(p, 'GCZ26.CMX', '1d', datetime(2026, 9, 1, tzinfo=timezone.utc),
                                 datetime(2026, 9, 8, 12, tzinfo=timezone.utc))


def test_missing_close_is_counted_and_retained():
    p = payload([epoch('2026-09-08T14:00:00Z')], closes=[None])
    frame, meta = normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                                            datetime(2026, 9, 8, 15, tzinfo=timezone.utc))
    assert pd.isna(frame.close.iloc[0])
    assert meta['missing_close_rows'] == 1


def test_non_numeric_source_value_is_rejected():
    p = payload([epoch('2026-09-08T14:00:00Z')])
    p['chart']['result'][0]['indicators']['quote'][0]['close'] = ['corrupt']
    with pytest.raises(ValueError, match='非数值'):
        normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                                 datetime(2026, 9, 8, 15, tzinfo=timezone.utc))


def test_excludes_bars_before_request_start():
    p = payload([epoch('2026-09-08T13:00:00Z'), epoch('2026-09-08T14:00:00Z')])
    frame, meta = normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, 30, tzinfo=timezone.utc),
                                            datetime(2026, 9, 8, 15, tzinfo=timezone.utc))
    assert len(frame) == 1
    assert meta['excluded'][0]['reason'] == ['before_request_start']


def test_rejects_more_than_sixty_days_for_five_minute():
    p = payload([epoch('2026-09-08T14:00:00Z')])
    with pytest.raises(ValueError, match='60 天'):
        normalize_yahoo_response(p, 'GCZ26.CMX', '5m', datetime(2026, 7, 1, tzinfo=timezone.utc),
                                 datetime(2026, 9, 8, tzinfo=timezone.utc))


def test_network_failure_is_reported_without_response_details(monkeypatch):
    def fail(*args, **kwargs):
        from curl_cffi import requests
        raise requests.exceptions.ConnectionError('private request details')
    monkeypatch.setattr('inv.gold_refresh_sources.requests.get', fail)
    with pytest.raises(ValueError, match='Yahoo 请求失败') as exc:
        fetch_yahoo('GCZ26.CMX', '5m', datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                    datetime(2026, 9, 8, 15, tzinfo=timezone.utc))
    assert 'private request details' not in str(exc.value)
