.PHONY: help setup check test analyze update render preview clean

PY           := .venv/bin/python
PNPM         := pnpm
VUEPRESS     := node_modules/.bin/vuepress
SITE_OUTPUT  := $(CURDIR)/_site
export MPLCONFIGDIR := $(CURDIR)/.cache/matplotlib

define DATA_STATUS_PY
from inv import config as C
rows = [("FRED   序列", C.RAW_FRED), ("FRED vintage", C.RAW_FRED_RELEASES), ("行情   品种", C.RAW_MARKET),
        ("A股    指数", C.RAW_CN), ("派生数据集", C.PROCESSED)]
for name, d in rows:
    files = sorted(d.glob("*.csv")) if d.exists() else []
    size = sum(f.stat().st_size for f in files) / 1024 / 1024
    print(f"{name} : {len(files):>3} 个文件, {size:>6.1f} MB")
try:
    import pandas as pd
    df = pd.read_csv(C.MACRO_DAILY, parse_dates=["date"], index_col="date",
                     usecols=lambda c: c in ("date", "gold"))
    print(f"数据集区间 : {df.index.min().date()} ~ {df.index.max().date()}  ({len(df)} 行)")
except Exception:
    print("数据集区间 : 未构建，请运行 make update")
endef
export DATA_STATUS_PY

help:
	@echo ""
	@echo "  投资研究工作空间 —— 可用命令"
	@echo ""
	@echo "  make setup                         安装 Python 与 Node 依赖"
	@echo "  make update                        抓取数据并重建派生数据集"
	@echo "  make analyze REPORT=<slug>         显式重算一篇研究快照"
	@echo "  make render                        构建并校验 VuePress 站点"
	@echo "  make preview                       启动本地 VuePress 热更新"
	@echo "  make check                         运行内容、类型、单元与资源检查"
	@echo "  make test                          运行 Python 与 Node 单元测试"
	@echo ""

setup:
	uv sync --locked
	$(PNPM) install --frozen-lockfile
	@$(MAKE) --no-print-directory check

check:
	@mkdir -p "$(MPLCONFIGDIR)"
	@echo "=== 环境 ==="
	@uv --version
	@test "$$(node -p 'process.versions.node')" = "22.18.0" || { echo "Node 必须为 22.18.0（当前 $$(node -p 'process.versions.node')）"; exit 1; }
	@node --version
	@$(PNPM) --version
	@test -x $(PY) || { echo "venv 不存在，请运行 make setup"; exit 1; }
	@$(PY) -c "import sys; print('python', sys.version.split()[0])"
	@echo ""
	@echo "=== Python ==="
	@$(PY) -c "import pandas,numpy,statsmodels,plotly,matplotlib,yfinance,fredapi,dotenv,tabulate,yaml,inv; print('核心依赖 OK')"
	@$(PY) -m compileall -q src scripts
	@$(PY) -m ruff check src scripts tests/python
	@$(PY) -m pytest -q
	@echo ""
	@echo "=== 内容与 VuePress ==="
	@test -x $(VUEPRESS) || { echo "Node 依赖不存在，请运行 make setup"; exit 1; }
	@node -p "'vuepress ' + require('./node_modules/vuepress/package.json').version"
	@$(PNPM) run check:content
	@$(PY) scripts/check_snapshots.py
	@$(PNPM) run typecheck
	@$(PNPM) test
	@echo ""
	@$(PY) -c "$$DATA_STATUS_PY" 2>/dev/null || echo "无法读取数据状态"

test:
	@$(PY) -m pytest -q
	@$(PNPM) test

analyze:
	@test -n "$(REPORT)" || { echo "用法：make analyze REPORT=<stable-slug>"; exit 2; }
	$(PY) scripts/analyze_report.py "$(REPORT)"

update:
	$(PY) scripts/update_all.py $(UPDATE_ARGS)

render: check
	@test "$(SITE_OUTPUT)" = "$(CURDIR)/_site"
	rm -rf "$(SITE_OUTPUT)"
	$(VUEPRESS) build .
	@$(PNPM) run check:site

preview:
	$(VUEPRESS) dev . --host 127.0.0.1 --port 8080

clean:
	@test "$(SITE_OUTPUT)" = "$(CURDIR)/_site"
	rm -rf "$(SITE_OUTPUT)" .cache
	find . -name "__pycache__" -type d -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@echo "已清理站点、缓存与 Python 字节码"
