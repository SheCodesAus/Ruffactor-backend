from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect


class BrowserLoginRedirectMiddleware:
    """Redirect unauthenticated browser navigations to the backend login page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_redirect(request):
            query = urlencode({"next": request.get_full_path()})
            return HttpResponseRedirect(f"{settings.LOGIN_URL}?{query}")
        return self.get_response(request)

    def _should_redirect(self, request):
        if request.user.is_authenticated:
            return False
        if request.method not in {"GET", "HEAD"}:
            return False
        if request.path == settings.LOGIN_URL:
            return False
        if settings.STATIC_URL and request.path.startswith(settings.STATIC_URL):
            return False

        accept_header = request.headers.get("Accept", "")
        fetch_mode = request.headers.get("Sec-Fetch-Mode", "")
        wants_html = "text/html" in accept_header or fetch_mode == "navigate"
        return wants_html
