"""Acquisition helpers for Phase 0 supplemental gold evidence."""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from curl_cffi import requests

from inv.gold_drivers import fedwatch, gld_holdings

GLD_ARCHIVE_URL = (
    'https://api.spdrgoldshares.com/api/v1/historical-archive'
    '?product=gld&exchange=NYSE&lang=en'
)
NY = ZoneInfo('America/New_York')
_ISSUER_HOSTS = {'spdrgoldshares.com', 'ssga.com'}


def _aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{label} 必须是带时区的 datetime')
    return value


def _official_url(url: str, base: str) -> str:
    absolute = urljoin(base, url)
    parsed = urlparse(absolute)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not any(host == domain or host.endswith('.' + domain) for domain in _ISSUER_HOSTS):
        raise ValueError('GLD档案下载链接不属于可核验的发行人域名')
    return absolute


def _xlsx_payload(response: object) -> bytes:
    content = response.content
    if not content.startswith(b'PK') or not zipfile.is_zipfile(io.BytesIO(content)):
        raise ValueError('GLD档案响应不是有效XLSX文件')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        if not {'[Content_Types].xml', 'xl/workbook.xml'} <= names:
            raise ValueError('GLD档案XLSX结构缺少工作簿文件')
    return content


def _download_archive(download_dir: Path) -> tuple[bytes, str]:
    download_dir.mkdir(parents=True, exist_ok=True)
    url = GLD_ARCHIVE_URL
    response = requests.get(url, timeout=30, impersonate='chrome', allow_redirects=False)
    if response.status_code in {301, 302, 303, 307, 308}:
        location = response.headers.get('location')
        if not location:
            raise ValueError('GLD档案响应重定向缺少目标链接')
        url = _official_url(location, url)
        response = requests.get(url, timeout=30, impersonate='chrome', allow_redirects=False)
    if response.status_code != 200:
        raise ValueError(f'GLD档案HTTP状态异常: {response.status_code}')
    if 'json' in response.headers.get('content-type', '').lower():
        try:
            payload = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as exc:
            raise ValueError('GLD档案端点返回无效JSON') from exc
        if not isinstance(payload, dict):
            raise ValueError('GLD档案JSON结构异常')
        candidate = next((payload.get(key) for key in ('downloadUrl', 'download_url', 'url')
                          if isinstance(payload.get(key), str)), None)
        if candidate is None:
            raise ValueError('GLD档案JSON没有下载链接')
        url = _official_url(candidate, response.url)
        response = requests.get(url, timeout=30, impersonate='chrome', allow_redirects=False)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get('location')
            if not location:
                raise ValueError('GLD档案下载重定向缺少目标链接')
            url = _official_url(location, url)
            response = requests.get(url, timeout=30, impersonate='chrome', allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f'GLD档案下载HTTP状态异常: {response.status_code}')
    content = _xlsx_payload(response)
    path = download_dir / 'spdr-gld-historical-archive.xlsx'
    path.write_bytes(content)
    return content, url


def fetch_gld(start: datetime, cutoff: datetime, download_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Fetch the issuer workbook and retain completed NYSE observations before the cutoff day."""
    start, cutoff = _aware(start, 'start'), _aware(cutoff, 'cutoff')
    if start >= cutoff:
        raise ValueError('请求起止时间顺序错误')
    content, final_url = _download_archive(Path(download_dir))
    raw_path = Path(download_dir) / 'spdr-gld-historical-archive.xlsx'
    try:
        raw = pd.read_excel(io.BytesIO(content), sheet_name='US GLD Historical Archive',
                            usecols=['Date', 'Tonnes of Gold'])
    except (ValueError, ImportError, zipfile.BadZipFile) as exc:
        raise ValueError('GLD档案缺少预期工作表或字段') from exc
    normalized = gld_holdings(raw)
    local_start = pd.Timestamp(start).tz_convert(NY).date()
    cutoff_ny_date = pd.Timestamp(cutoff).tz_convert(NY).date()
    keep = [(local_start <= d.date() < cutoff_ny_date) for d in normalized.index]
    selected = normalized.loc[keep].copy()
    selected.insert(0, 'date', [d.date().isoformat() for d in selected.index])
    selected = selected.reset_index(drop=True)[['date', 'tonnes', 'holiday']]
    metadata = {
        'source': 'SPDR Gold Shares historical archive',
        'source_url': final_url,
        'requested_url': GLD_ARCHIVE_URL,
        'retrieved_at': datetime.now().astimezone().isoformat(),
        'first_publication_at': None,
        'first_publication_at_status': 'unknown',
        'observation_date_field': 'Date',
        'observation_frequency': 'NYSE trading-day daily archive',
        'worksheet': 'US GLD Historical Archive',
        'retained_rows': len(selected),
        'raw_file': raw_path.name,
        'sha256': hashlib.sha256(content).hexdigest(),
    }
    return selected, metadata


def normalize_fedwatch(frame: pd.DataFrame, meeting: str, cutoff: datetime,
                       policy_ranges: pd.DataFrame,
                       announcement_dates: tuple[str, ...] = ()) -> pd.DataFrame:
    """Validate a meeting-specific export and calculate move buckets against each date's policy."""
    cutoff = _aware(cutoff, 'cutoff')
    meeting_date = pd.Timestamp(meeting).date()
    announcement_days = {pd.Timestamp(day).date() for day in announcement_dates}
    # Reuse the established parser and strict distribution checks. Choose an observed band as its
    # validation anchor, then recompute the derived columns below from each date's policy range.
    source_bands = [col for col in frame.columns if re.fullmatch(r'\(\d+-\d+\)', str(col))]
    if not source_bands:
        raise ValueError('FedWatch缺少利率区间概率列')
    anchor = re.fullmatch(r'\((\d+)-(\d+)\)', source_bands[0])
    checked = fedwatch(frame, current=(int(anchor.group(1)), int(anchor.group(2))))
    dates = checked.index
    last_complete = pd.Timestamp(cutoff).tz_convert(NY).date()
    keep = np.array([(d.date() < meeting_date) and (d.date() < last_complete) for d in dates])
    checked = checked.loc[keep].copy()
    if not {'date', 'lower_bp', 'upper_bp'} <= set(policy_ranges.columns):
        raise ValueError('政策区间表必须包含date/lower_bp/upper_bp')
    policies = policy_ranges[['date', 'lower_bp', 'upper_bp']].copy()
    policies['date'] = pd.to_datetime(policies.date, errors='raise').dt.normalize()
    policies['lower_bp'] = pd.to_numeric(policies.lower_bp, errors='raise')
    policies['upper_bp'] = pd.to_numeric(policies.upper_bp, errors='raise')
    if policies.date.duplicated().any() or policies.empty:
        raise ValueError('政策区间生效日期缺失或重复')
    if ((policies.lower_bp % 25 != 0) | (policies.upper_bp - policies.lower_bp != 25)).any():
        raise ValueError('政策目标区间必须为25基点网格')
    policies = policies.sort_values('date').reset_index(drop=True)
    if policies.lower_bp.isna().any() or policies.upper_bp.isna().any():
        raise ValueError('政策目标区间不能缺失')
    bands = {}
    for col in checked.columns:
        match = re.fullmatch(r'\((\d+)-(\d+)\)', col)
        if match:
            bands[col] = tuple(map(int, match.groups()))
    values = checked[list(bands)].copy()
    results: list[tuple[float, float, float, bool]] = []
    for observation in checked.index:
        day = observation.normalize()
        applicable = policies.loc[policies.date <= day]
        if applicable.empty:
            raise ValueError(f'缺少{day.date()}前已生效的政策目标区间')
        current = applicable.iloc[-1]
        changed_today = (
            len(applicable) > 1 and current.date == day
            and applicable.iloc[-2].lower_bp != current.lower_bp
        )
        current_band = (int(current.lower_bp), int(current.upper_bp))
        if changed_today or day.date() in announcement_days:
            results.append((np.nan, np.nan, np.nan, True))
            continue
        if current_band not in bands.values():
            raise ValueError(f'FedWatch缺少当日目标区间{current_band}')
        lower_cols = [c for c, (_, high) in bands.items() if high <= current_band[0]]
        same_cols = [c for c, band in bands.items() if band == current_band]
        higher_cols = [c for c, (low, _) in bands.items() if low >= current_band[1]]
        results.append((float(values.loc[observation, lower_cols].sum(min_count=1) * 100) if lower_cols else np.nan,
                        float(values.loc[observation, same_cols].sum(min_count=1) * 100) if same_cols else np.nan,
                        float(values.loc[observation, higher_cols].sum(min_count=1) * 100) if higher_cols else np.nan,
                        False))
    checked['lower_pct'] = [r[0] for r in results]
    checked['unchanged_pct'] = [r[1] for r in results]
    checked['higher_pct'] = [r[2] for r in results]
    checked['ambiguous_policy_day'] = [r[3] for r in results]
    return checked
