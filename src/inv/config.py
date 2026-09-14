"""路径常量、数据序列清单与品种映射。

本模块是路径与原始数据序列的**单一事实来源**：新增序列在此登记后，
抓取脚本会自动纳入；派生变换策略由 dataset.py 统一定义。

路径全部基于项目根目录动态推导（pathlib），不写死绝对路径，
因此整个工作空间可以随意移动或改名。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

# 本文件位于 <root>/src/inv/config.py，故上溯三级得到项目根
ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data"
RAW = DATA / "raw"
RAW_FRED = RAW / "fred"
RAW_FRED_RELEASES = RAW / "fred_first_release"
RAW_MARKET = RAW / "market"
RAW_CN = RAW / "cn"
PROCESSED = DATA / "processed"

CONTENT = ROOT / "content"
CONTENT_ASSETS = CONTENT / "_assets"

# 主数据集
MACRO_DAILY = PROCESSED / "macro_daily.csv"
MACRO_WEEKLY = PROCESSED / "macro_weekly.csv"
MACRO_MONTHLY = PROCESSED / "macro_monthly.csv"
MACRO_OBSERVATION_DAILY = PROCESSED / "macro_observation_daily.csv"
MACRO_OBSERVATION_WEEKLY = PROCESSED / "macro_observation_weekly.csv"
MACRO_OBSERVATION_MONTHLY = PROCESSED / "macro_observation_monthly.csv"

def ensure_dirs() -> None:
    """确保所有需要写入的目录存在。"""
    for d in (RAW_FRED, RAW_FRED_RELEASES, RAW_MARKET, RAW_CN, PROCESSED):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 密钥
# ---------------------------------------------------------------------------

load_dotenv(ROOT / ".env")


def fred_api_key() -> str | None:
    """返回 FRED API Key；未配置时返回 None（调用方应降级而非崩溃）。"""
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key or key == "your_fred_api_key_here":
        return None
    return key


FRED_KEY_HELP = (
    "未检测到有效的 FRED_API_KEY。\n"
    "  1. 免费申请: https://fred.stlouisfed.org/docs/api/api_key.html\n"
    "  2. 将 .env.example 复制为 .env\n"
    "  3. 填入 FRED_API_KEY=你的密钥"
)


# ---------------------------------------------------------------------------
# 数据起点
# ---------------------------------------------------------------------------

START_DATE = "1990-01-01"


# ---------------------------------------------------------------------------
# FRED 序列清单
# ---------------------------------------------------------------------------
# 格式: 序列ID -> (输出列名, 中文说明, 单位, 原始频率)

FRED_SERIES: dict[str, tuple[str, str, str, str]] = {
    # --- 政策利率与美联储工具 ---
    "DFF": ("ffr_effective", "有效联邦基金利率", "%", "D"),
    "DFEDTARU": ("ffr_target_upper", "联邦基金目标区间上限", "%", "D"),
    "DFEDTARL": ("ffr_target_lower", "联邦基金目标区间下限", "%", "D"),
    "IORB": ("iorb", "准备金余额利率", "%", "D"),
    "RRPONTSYD": ("on_rrp", "隔夜逆回购用量", "十亿美元", "D"),
    "WALCL": ("fed_assets", "美联储总资产", "百万美元", "W"),
    # --- 美债收益率与曲线 ---
    "DGS2": ("ust2y", "2年期国债收益率", "%", "D"),
    "DGS10": ("ust10y", "10年期国债收益率", "%", "D"),
    "DGS30": ("ust30y", "30年期国债收益率", "%", "D"),
    "T10Y2Y": ("curve_10y2y", "10Y-2Y 期限利差", "%", "D"),
    "T10Y3M": ("curve_10y3m", "10Y-3M 期限利差", "%", "D"),
    # --- 实际利率与通胀预期（黄金定价核心）---
    "DFII10": ("real10y", "10年期 TIPS 实际利率", "%", "D"),
    "DFII5": ("real5y", "5年期 TIPS 实际利率", "%", "D"),
    "T10YIE": ("breakeven10y", "10年盈亏平衡通胀预期", "%", "D"),
    "T5YIFR": ("fwd5y5y", "5年后5年远期通胀预期", "%", "D"),
    # --- 美元 ---
    "DTWEXBGS": ("usd_broad", "广义贸易加权美元指数", "指数", "D"),
    "DTWEXAFEGS": ("usd_afe", "发达经济体美元指数", "指数", "D"),
    # --- 通胀 ---
    "CPIAUCSL": ("cpi", "CPI 城市消费者（季调）", "指数", "M"),
    "CPILFESL": ("cpi_core", "核心 CPI（季调）", "指数", "M"),
    "PCEPILFE": ("pce_core", "核心 PCE 物价指数", "指数", "M"),
    # --- 就业与增长 ---
    "UNRATE": ("unemployment", "失业率", "%", "M"),
    "PAYEMS": ("nonfarm_payroll", "非农就业人数", "千人", "M"),
    "ICSA": ("initial_claims", "初次失业申请（季调）", "人", "W"),
    "GDPC1": ("gdp_real", "实际 GDP", "十亿美元(2017)", "Q"),
    # --- 信用与流动性 ---
    "BAMLH0A0HYM2": ("hy_spread", "美国高收益债信用利差", "%", "D"),
    "NFCI": ("nfci", "芝加哥联储全国金融状况指数", "指数", "W"),
    # --- 大宗与其他 ---
    "DCOILWTICO": ("wti", "WTI 原油现货价", "美元/桶", "D"),
    "DEXCHUS": ("usdcny", "美元兑人民币", "CNY/USD", "D"),
}

# A released macro value may remain current until the next observation. These
# limits are calendar days, not row counts, and prevent stale values from being
# silently treated as current when a feed stops updating.
FRED_MAX_AGE_DAYS = {"D": 7, "W": 21, "M": 62, "Q": 140}


# ---------------------------------------------------------------------------
# yfinance 品种清单
# ---------------------------------------------------------------------------
# 格式: ticker -> (输出列名, 中文说明, 资产类别)

YF_TICKERS: dict[str, tuple[str, str, str]] = {
    # --- 黄金及贵金属 ---
    "GC=F": ("gold", "COMEX 黄金连续期货", "metal"),
    "SI=F": ("silver", "COMEX 白银连续期货", "metal"),
    "GLD": ("gld", "SPDR 黄金 ETF", "metal"),
    # --- 美元与汇率 ---
    "DX-Y.NYB": ("dxy", "美元指数 DXY", "fx"),
    "EURUSD=X": ("eurusd", "欧元兑美元", "fx"),
    "USDJPY=X": ("usdjpy", "美元兑日元", "fx"),
    "USDCNY=X": ("usdcny_yf", "美元兑人民币(离岸参考)", "fx"),
    # --- 美债 ETF ---
    "TLT": ("tlt", "20年+ 美国国债 ETF", "bond"),
    "IEF": ("ief", "7-10年 美国国债 ETF", "bond"),
    "TIP": ("tip", "通胀保值债券 ETF", "bond"),
    "LQD": ("lqd", "投资级公司债 ETF", "bond"),
    "HYG": ("hyg", "高收益债 ETF", "bond"),
    # --- 美股 ---
    "^GSPC": ("spx", "标普500指数", "equity_us"),
    "^NDX": ("ndx", "纳斯达克100指数", "equity_us"),
    "^DJI": ("dji", "道琼斯工业指数", "equity_us"),
    "^RUT": ("rut", "罗素2000指数", "equity_us"),
    "^VIX": ("vix", "VIX 波动率指数", "equity_us"),
    "SPY": ("spy", "标普500 ETF", "equity_us"),
    "QQQ": ("qqq", "纳斯达克100 ETF", "equity_us"),
    # --- 大宗 ---
    "CL=F": ("wti_yf", "WTI 原油期货", "commodity"),
    "HG=F": ("copper", "COMEX 铜期货", "commodity"),
    # --- A股（yfinance 备用通道）---
    "000001.SS": ("sse_yf", "上证指数(yf备用)", "equity_cn"),
    "000300.SS": ("csi300_yf", "沪深300(yf备用)", "equity_cn"),
    "^HSI": ("hsi", "恒生指数", "equity_cn"),
}


# ---------------------------------------------------------------------------
# A股清单（akshare 主通道）
# ---------------------------------------------------------------------------
# 格式: 指数代码 -> (输出列名, 中文说明)

CN_INDEXES: dict[str, tuple[str, str]] = {
    "sh000001": ("sse", "上证指数"),
    "sh000300": ("csi300", "沪深300"),
    "sh000905": ("csi500", "中证500"),
    "sz399006": ("chinext", "创业板指"),
    "sh000688": ("star50", "科创50"),
}

# 黄金研究采用独立的定时快照，不改变 gold=GC=F 或公共 SPX 日历。
GOLD_RESEARCH_RAW = RAW / "gold-outlook"
GOLD_RESEARCH_PRIMARY = "gold"
GOLD_RESEARCH_FUTURES = {"gold": "GC=F", "gcv26": "GCV26.CMX", "gcz26": "GCZ26.CMX"}
GOLD_RESEARCH_INTRADAY = {
    "primary": "gcz26", "interval": "5m", "timezone": "America/New_York",
    "start": "2026-07-30T18:00:00-04:00", "end": "2026-09-08T17:00:00-04:00",
    "unit": "USD/troy oz", "source": "https://finance.yahoo.com/quote/GCZ26.CMX/history/",
}
GOLD_RESEARCH_FRED_IDS = (
    "DFF", "DFEDTARU", "DFEDTARL", "DGS2", "DGS10", "DFII10", "DFII5", "T10YIE",
    "DTWEXBGS", "CPIAUCSL", "CPILFESL", "PCEPILFE", "UNRATE", "PAYEMS", "ICSA", "DCOILWTICO",
)
# Phase 2 定向补充；复用已登记的 Yahoo 品种，不更新共享 raw。
GOLD_RESEARCH_DRIVER_MARKETS = {"dxy": "DX-Y.NYB", "wti_futures": "CL=F"}
GOLD_RESEARCH_FEDWATCH_MEETINGS = ("2026-09-16", "2026-10-28", "2026-12-09")
# 字段 -> (品种说明, 单位, 频率, 来源入口)。这些候选尚未获得公开数值发布许可。
GOLD_RESEARCH_CANDIDATES = {
    "gold": ("COMEX 黄金期货（已选主对象；接续与 Close 口径待核验）", "USD/troy oz", "D",
             "https://finance.yahoo.com/quote/GC%3DF/history/"),
    "xauusd": ("美元计价现货黄金（补充参照）", "USD/troy oz", "D",
               "https://www.dukascopy.com/swiss/english/marketwatch/historical/"),
    "dxy": ("美元指数 DXY", "index", "D", "https://finance.yahoo.com/quote/DX-Y.NYB/history/"),
    "policy_expectations": ("按会议区分的政策利率预期", "%", "D",
                            "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"),
    "etf_global": ("全球实物黄金 ETF 持金量与资金流", "tonnes; USD", "W/M",
                   "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows"),
    "etf_gld": ("SPDR Gold Shares 持金量", "tonnes", "D", "https://www.spdrgoldshares.com/usa/gld/"),
    "comex_activity": ("COMEX 黄金合约成交量与未平仓量", "contracts", "D",
                       "https://www.cmegroup.com/markets/metals/precious/gold.volume.html"),
}



def series_meta() -> dict[str, dict[str, str]]:
    """汇总所有字段的元信息，供 SOURCES.md 生成与文档引用。"""
    meta: dict[str, dict[str, str]] = {}
    for sid, (col, desc, unit, freq) in FRED_SERIES.items():
        meta[col] = {
            "source": "FRED",
            "source_id": sid,
            "description": desc,
            "unit": unit,
            "frequency": freq,
        }
    for tk, (col, desc, cls) in YF_TICKERS.items():
        meta[col] = {
            "source": "Yahoo Finance",
            "source_id": tk,
            "description": desc,
            "unit": "价格/指数点",
            "frequency": "D",
            "asset_class": cls,
        }
    for code, (col, desc) in CN_INDEXES.items():
        meta[col] = {
            "source": "AkShare",
            "source_id": code,
            "description": desc,
            "unit": "指数点",
            "frequency": "D",
            "asset_class": "equity_cn",
        }
    return meta


# ---------------------------------------------------------------------------
# 中文标签（供图表图例、表格表头使用）
# ---------------------------------------------------------------------------

# 简短标签覆盖：series_meta 里的描述偏长，图例用简称更清晰
_LABEL_OVERRIDE: dict[str, str] = {
    "gold": "黄金",
    "silver": "白银",
    "dxy": "美元指数",
    "usd_broad": "广义美元指数",
    "real10y": "10Y实际利率",
    "real5y": "5Y实际利率",
    "ust2y": "2Y美债",
    "ust10y": "10Y美债",
    "ust30y": "30Y美债",
    "breakeven10y": "10Y通胀预期",
    "fwd5y5y": "5Y5Y远期通胀预期",
    "curve_10y2y": "10Y-2Y利差",
    "curve_10y3m": "10Y-3M利差",
    "ffr_effective": "联邦基金利率",
    "ffr_target_upper": "目标区间上限",
    "ffr_target_lower": "目标区间下限",
    "iorb": "准备金利率",
    "fed_assets": "美联储总资产",
    "on_rrp": "隔夜逆回购",
    "hy_spread": "高收益债利差",
    "spx": "标普500",
    "ndx": "纳斯达克100",
    "dji": "道指",
    "rut": "罗素2000",
    "vix": "VIX",
    "tlt": "长端美债ETF",
    "ief": "中端美债ETF",
    "tip": "TIPS ETF",
    "sse": "上证指数",
    "csi300": "沪深300",
    "csi500": "中证500",
    "chinext": "创业板指",
    "star50": "科创50",
    "hsi": "恒生指数",
    "wti": "WTI原油",
    "copper": "铜",
    "cpi": "CPI",
    "cpi_core": "核心CPI",
    "pce_core": "核心PCE",
    "unemployment": "失业率",
    "nonfarm_payroll": "非农就业",
    "usdcny": "美元兑人民币",
    "eurusd": "欧元兑美元",
    "usdjpy": "美元兑日元",
    "ratio_gold_silver": "金银比",
    "ratio_gold_spx": "金/标普比",
}


def labels() -> dict[str, str]:
    """返回 {字段名: 中文标签} 全映射，含 ret_ / d_ 派生字段。

    未登记的字段回退到 series_meta 的描述，最后回退到字段名本身。
    """
    meta = series_meta()
    out: dict[str, str] = {}

    for col, info in meta.items():
        out[col] = _LABEL_OVERRIDE.get(col, info["description"])
    out.update(_LABEL_OVERRIDE)

    # 派生字段标签
    base = dict(out)
    for col, lab in base.items():
        out[f"ret_{col}"] = f"{lab}收益率"
        out[f"d_{col}"] = f"{lab}变动"

    return out


def label(col: str) -> str:
    """单字段中文标签。"""
    return labels().get(col, col)
