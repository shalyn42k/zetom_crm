# claude — one place for the upload limits. Files are accepted on the public
# form (anonymous), on the request card and in the document window; before,
# only the document window checked the size and the public form took any
# number of files of any size from anyone.
from django.conf import settings
from django.utils.translation import gettext as _


def max_upload_bytes():
    return settings.MAX_UPLOAD_MB * 1024 * 1024


def upload_errors(files, max_files=None):
    """Error messages for a list of uploaded files ([] = all fine)."""
    errors = []
    if max_files is not None and len(files) > max_files:
        errors.append(_("Too many files (max %(n)d).") % {"n": max_files})
    too_big = [f.name for f in files if f.size > max_upload_bytes()]
    if too_big:
        errors.append(
            _("Too large (max %(mb)d MB): %(names)s")
            % {"mb": settings.MAX_UPLOAD_MB, "names": ", ".join(too_big)}
        )
    return errors
