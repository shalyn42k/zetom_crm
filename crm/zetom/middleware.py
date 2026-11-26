# claude — opens the per-request cache used by department_choices()
# (crm/zetom/models.py). A ContextVar, so threads/requests never share it.
from crm.zetom.models import _request_cache


class RequestCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request_cache.set({})
        try:
            return self.get_response(request)
        finally:
            _request_cache.reset(token)
