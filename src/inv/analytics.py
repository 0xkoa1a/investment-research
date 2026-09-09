"""分析工具：相关性、滚动回归、regime 切分、绩效统计。

方法论要点（避免常见陷阱）:

  1. **不要用价格水平算相关性**。价格是非平稳序列，两条各自带趋势的序列
     会得到虚高的相关系数（伪相关）。本模块所有相关性函数都要求传入
     收益率或差分序列，函数名以 _ret 提示。

  2. **相关性是时变的**，单一静态数字信息量很低。优先使用 rolling_corr
     观察相关性本身的演变。

  3. **回归要看残差**。α 显著非零说明存在解释变量之外的驱动力，
     这往往是真正值得研究的地方。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 年化因子
ANNUAL_D = 252
ANNUAL_W = 52
ANNUAL_M = 12


# ---------------------------------------------------------------------------
# 相关性
# ---------------------------------------------------------------------------


def corr_matrix(df: pd.DataFrame, cols: list[str] | None = None, *, method: str = "pearson") -> pd.DataFrame:
    """收益率序列的相关矩阵。

    警告: 传入的列应为收益率/差分（ret_* 或 d_*），不要传价格水平。
    """
    sub = df[cols] if cols else df
    return sub.corr(method=method)


def rolling_corr(
    a: pd.Series,
    b: pd.Series,
    windows: tuple[int, ...] = (60, 250),
) -> pd.DataFrame:
    """多窗口滚动相关性。

    Args:
        a, b:    收益率序列（非价格）。
        windows: 窗口长度（交易日）。60 ≈ 3个月, 250 ≈ 1年。

    Returns:
        DataFrame，列名如 corr_60d / corr_250d。
    """
    out = pd.DataFrame(index=a.index)
    for w in windows:
        out[f"corr_{w}d"] = a.rolling(w, min_periods=int(w * 0.7)).corr(b)
    return out


# ---------------------------------------------------------------------------
# 滚动回归
# ---------------------------------------------------------------------------


def rolling_beta(
    y: pd.Series,
    x: pd.Series,
    window: int = 250,
) -> pd.DataFrame:
    """滚动单变量回归 y = alpha + beta * x + eps。

    用协方差/方差的滚动计算实现，比逐窗口跑 OLS 快数十倍，结果等价。

    Returns:
        DataFrame(alpha, beta, r2)。alpha 已年化（× 252）。
    """
    df = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if df.empty:
        return pd.DataFrame(columns=["alpha", "beta", "r2"])

    mp = int(window * 0.7)
    roll = df.rolling(window, min_periods=mp)

    var_x = roll["x"].var()
    cov_xy = df["x"].rolling(window, min_periods=mp).cov(df["y"])
    beta = cov_xy / var_x
    alpha = roll["y"].mean() - beta * roll["x"].mean()

    corr = df["x"].rolling(window, min_periods=mp).corr(df["y"])

    out = pd.DataFrame(
        {
            "alpha": alpha * ANNUAL_D,  # 年化，便于解读
            "beta": beta,
            "r2": corr**2,
        }
    )
    return out.reindex(y.index)


def ols_summary(
    df: pd.DataFrame,
    y_col: str,
    x_cols: list[str],
    *,
    hac_lags: int | None = 5,
) -> dict:
    """多元 OLS 回归，返回结构化结果（供表格展示）。

    使用 HAC (Newey-West) 稳健标准误 —— 金融时间序列普遍存在
    异方差与自相关，普通标准误会低估不确定性。

    Args:
        hac_lags: Newey-West 滞后阶数；None 表示用普通标准误。

    Returns:
        dict 含 nobs / r2 / adj_r2 / params / tvalues / pvalues / resid / fitted / model
    """
    import statsmodels.api as sm

    sub = df[[y_col, *x_cols]].dropna()
    if sub.empty or len(sub) < len(x_cols) + 5:
        raise ValueError(f"有效样本不足: {len(sub)} 行")

    y = sub[y_col]
    X = sm.add_constant(sub[x_cols])

    model = sm.OLS(y, X)
    if hac_lags:
        res = model.fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    else:
        res = model.fit()

    return {
        "nobs": int(res.nobs),
        "r2": float(res.rsquared),
        "adj_r2": float(res.rsquared_adj),
        "params": res.params,
        "tvalues": res.tvalues,
        "pvalues": res.pvalues,
        "resid": res.resid,
        "fitted": res.fittedvalues,
        "model": res,
        "period": (sub.index.min(), sub.index.max()),
    }


def coef_table(res: dict, *, digits: int = 4) -> pd.DataFrame:
    """把 ols_summary 结果整理成可读的系数表。"""
    tbl = pd.DataFrame(
        {
            "系数": res["params"],
            "t值": res["tvalues"],
            "p值": res["pvalues"],
        }
    )
    tbl["显著性"] = pd.cut(
        tbl["p值"],
        bins=[-0.001, 0.01, 0.05, 0.10, 1.0],
        labels=["***", "**", "*", ""],
        ordered=False,
    ).astype(str).replace("nan", "")
    return tbl.round(digits)


# ---------------------------------------------------------------------------
# Regime 切分
# ---------------------------------------------------------------------------


def policy_regime(df: pd.DataFrame, rate_col: str = "ffr_effective", *, window: int = 90, threshold: float = 0.10) -> pd.Series:
    """根据政策利率变动方向切分货币政策周期。

    逻辑: 用 window 天的利率变动判断方向，变动幅度小于 threshold 视为持稳。

    Args:
        rate_col:  政策利率字段。
        window:    判断窗口（交易日）。
        threshold: 判定阈值（百分点）。

    Returns:
        Series，取值 hiking / cutting / holding。
    """
    if rate_col not in df.columns:
        return pd.Series(index=df.index, dtype="object")

    chg = df[rate_col].diff(window)
    regime = pd.Series("holding", index=df.index, dtype="object")
    regime[chg > threshold] = "hiking"
    regime[chg < -threshold] = "cutting"
    regime[chg.isna()] = np.nan
    return regime


def balance_sheet_regime(df: pd.DataFrame, col: str = "fed_assets", *, window: int = 90, threshold: float = 0.01) -> pd.Series:
    """根据美联储资产负债表变动切分 QE / QT / neutral。

    Args:
        threshold: window 期间总资产变动比例阈值（0.01 = 1%）。
    """
    if col not in df.columns:
        return pd.Series(index=df.index, dtype="object")

    pct = df[col].pct_change(window)
    regime = pd.Series("neutral", index=df.index, dtype="object")
    regime[pct > threshold] = "QE"
    regime[pct < -threshold] = "QT"
    regime[pct.isna()] = np.nan
    return regime


def regime_stats(
    df: pd.DataFrame,
    regime: pd.Series,
    ret_cols: list[str],
    *,
    periods_per_year: int = ANNUAL_D,
) -> pd.DataFrame:
    """按 regime 分组统计各资产的年化收益与波动。

    Returns:
        MultiIndex 列 (资产, 指标) 的统计表。
    """
    data = df[ret_cols].copy()
    data["_regime"] = regime

    rows = []
    for name, grp in data.groupby("_regime", dropna=True):
        rec: dict[str, object] = {"regime": name, "天数": len(grp)}
        for c in ret_cols:
            s = grp[c].dropna()
            if s.empty:
                rec[f"{c}_年化收益"] = np.nan
                rec[f"{c}_年化波动"] = np.nan
                continue
            rec[f"{c}_年化收益"] = s.mean() * periods_per_year
            rec[f"{c}_年化波动"] = s.std() * np.sqrt(periods_per_year)
        rows.append(rec)

    out = pd.DataFrame(rows).set_index("regime")
    return out.round(4)


# ---------------------------------------------------------------------------
# 绩效统计
# ---------------------------------------------------------------------------


def drawdown(prices: pd.Series) -> pd.Series:
    """回撤序列（相对历史高点的百分比，负值）。"""
    s = prices.dropna()
    return s / s.cummax() - 1.0


def perf_stats(ret: pd.Series, *, periods_per_year: int = ANNUAL_D) -> dict[str, float]:
    """收益率序列的基础绩效指标。

    Args:
        ret: 对数收益率序列。
    """
    s = ret.dropna()
    if s.empty:
        return {}

    ann_ret = s.mean() * periods_per_year
    ann_vol = s.std() * np.sqrt(periods_per_year)
    cum = s.cumsum().apply(np.exp)

    return {
        "年化收益": round(float(ann_ret), 4),
        "年化波动": round(float(ann_vol), 4),
        "夏普(rf=0)": round(float(ann_ret / ann_vol), 3) if ann_vol > 0 else np.nan,
        "最大回撤": round(float(drawdown(cum).min()), 4),
        "累计收益": round(float(cum.iloc[-1] - 1), 4),
        "样本数": int(len(s)),
    }


def summary_by_asset(df: pd.DataFrame, ret_cols: list[str], *, periods_per_year: int = ANNUAL_D) -> pd.DataFrame:
    """多资产绩效对比表。"""
    rows = {}
    for c in ret_cols:
        if c in df.columns:
            stats = perf_stats(df[c], periods_per_year=periods_per_year)
            if stats:
                rows[c.replace("ret_", "")] = stats
    return pd.DataFrame(rows).T
