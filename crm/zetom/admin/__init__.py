"""zetom admin package — split per-ModelAdmin for readability.

Importing each submodule triggers the @admin.register() decorators.
Order matters only in that base.py must be first (other modules
import from it).
"""
from .base import BaseRequestAdmin, DepartmentsDisplayMixin, ReasonForm
from . import children  # noqa: F401
from . import deletedrequest  # noqa: F401
from . import log  # noqa: F401
from . import requestmain  # noqa: F401
from . import requestnull  # noqa: F401

__all__ = ["BaseRequestAdmin", "DepartmentsDisplayMixin", "ReasonForm"]
