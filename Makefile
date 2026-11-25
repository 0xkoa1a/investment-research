.PHONY: setup check test preview render export

setup:
	pnpm install --frozen-lockfile

check:
	pnpm run check:content
	pnpm run typecheck
	$(MAKE) test

test:
	pnpm test

preview:
	pnpm exec vuepress dev . --host 127.0.0.1 --port 8080

render: check
	pnpm run docs:build --clean-temp --clean-cache
	pnpm run check:site

export:
	@test -n "$(PAGE)" || { echo "用法：make export PAGE=gold-evidence.md"; exit 2; }
	pnpm run export:page -- --page "$(PAGE)" $(if $(filter 1,$(ALLOW_EXTERNAL)),--allow-external,)
