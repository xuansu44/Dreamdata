"""Sphinx configuration for dreamdata."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

# -- Project information -----------------------------------------------------
project = "dreamdata"
author = "dreamdata"
release = "0.1.0"

# -- Bilingual configuration --------------------------------------------------
language = "en"
locale_dirs = ["../locales/"]
gettext_compact = False

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]
templates_path = ["_templates"]
exclude_patterns: list[str] = ["zh_CN/**"]

# MyST ---------------------------------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "substitution",
]
myst_heading_anchors = 3

# -- Options for HTML output -------------------------------------------------
html_theme = "furo"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "source_repository": "https://github.com/xuansu44/Dreamdata",
    "source_branch": "main",
    "source_directory": "docs/source/",
}

# Language switcher for bilingual docs
html_context = {
    "languages": [
        ("en", "English", ""),
        ("zh_CN", "简体中文", "zh_CN/"),
    ],
    "current_language": language,
}

# -- Autodoc -----------------------------------------------------------------
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False

# -- Intersphinx -------------------------------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
}
