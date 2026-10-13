.PHONY: help setup install-hooks badge bump test

help:
	@echo "wbuch (simple-wb) — Fast German vocabulary input & dictionary"
	@echo ""
	@echo "  make setup          Setup git hooks & submodule"
	@echo "  make install-hooks  Install pre-push git hook"
	@echo "  make badge          Regenerate public/logo.svg and public/badge.svg"
	@echo "  make bump [V=x.y.z] Bump version, regenerate assets, commit"
	@echo "  make test           Run tests"

setup:
	git -c protocol.file.allow=always submodule update --init
	$(MAKE) install-hooks
	@echo "✓ Setup complete"

install-hooks:
	cp .github/hooks/pre-push .git/hooks/pre-push
	chmod +x .git/hooks/pre-push
	@echo "✓ Pre-push hook installed"

badge:
	@node tools/generate_logo.mjs

bump:
	@node tools/bump.mjs $(V)

test:
	pytest tests/
