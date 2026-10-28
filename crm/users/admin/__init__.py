"""users admin package — split per-ModelAdmin for readability.

Importing each submodule triggers the @admin.register() decorators
(or the explicit admin.site.register call for the auth.User override).
"""
from . import \
    otp  # noqa: F401  # claude — Polish labels on the 2FA device pages
from . import role  # noqa: F401
from . import user  # noqa: F401
from . import userprofile  # noqa: F401
