.PHONY: check help

help:
	@echo "Cibles utiles :"
	@echo "  make check   - même logique que les jobs test-backend + test-frontend (CI)"
	@echo "  (équivalent : npm run ci:check à la racine)"

check:
	node scripts/ci-check.mjs
