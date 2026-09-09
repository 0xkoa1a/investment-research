"""投资研究工作空间核心包。

模块职责:
    config    : 路径常量、数据序列清单、品种映射（单一事实来源）
    storage   : CSV 读写、增量合并、重试封装
    fetch_*   : 各数据源抓取（fetch_fred / fetch_market / fetch_cn）
    dataset   : 多频率对齐、重采样、派生指标
    analytics : 滚动相关、滚动 beta、regime 切分、绩效统计
    viz       : 统一图表样式（Plotly + matplotlib）

注意: 数据读写模块命名为 storage 而非 io，以避免与 Python 标准库 io 混淆。
"""

__version__ = "0.1.0"

from inv import analytics, config, dataset, storage, viz

__all__ = ["config", "storage", "dataset", "analytics", "viz"]
