# pylint: skip-file

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "FoundryTools"
copyright = "2024, ftCLI"
author = "ftCLI"
release = "0.1.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc", "sphinx.ext.viewcode"]

templates_path = ["_templates"]
exclude_patterns = []  # type: ignore
# -- Options for HTML output -------------------------------------------------
autodoc_default_options = {
    "members": True,
    "private-members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

autodoc_typehints = "description"
autodoc_class_signature = "separated"
html_static_path = ["_static"]
html_theme = "sphinx_rtd_theme"
