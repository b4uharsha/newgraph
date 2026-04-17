"""Notebook styling resources."""

from importlib import resources


def get_notebook_css() -> str:
    """Load the notebook CSS from package resources."""
    return resources.files(__package__).joinpath("notebook.css").read_text()
