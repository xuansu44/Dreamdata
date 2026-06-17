# Minimal makefile for Sphinx documentation (bilingual)

SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  html       to make English standalone HTML"
	@echo "  html-zh    to make Chinese standalone HTML"
	@echo "  html-all   to make both English and Chinese HTML"
	@echo "  serve      to serve both docs on http://localhost:8000"
	@echo "  clean      to remove the build directory"

.PHONY: help Makefile

html:
	@uv run $(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

html-zh:
	@uv run $(SPHINXBUILD) -M html "$(SOURCEDIR)/zh_CN" "$(BUILDDIR)/html/zh_CN" $(SPHINXOPTS)

html-all: html html-zh

serve: html-all
	@echo "Serving docs at http://localhost:8000"
	@echo "  English: http://localhost:8000"
	@echo "  Chinese: http://localhost:8000/zh_CN"
	@cd "$(BUILDDIR)/html" && python -m http.server 8000

clean:
	rm -rf "$(BUILDDIR)"
