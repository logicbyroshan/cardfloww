# Compatibility shim for tests that import config.urls_panel
from django.http import HttpResponse, HttpResponseNotFound
from config import urls as _urls

# Prefer the real implementation when available in config.urls
try:
    from config.urls import _protected_media_serve
except Exception:
    def _protected_media_serve(request, path, document_root=None):
        return HttpResponseNotFound()

# Provide a simple robots.txt response for panel host tests
def panel_robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /", content_type='text/plain')

# Expose urlpatterns from main urls to preserve routing compatibility
urlpatterns = getattr(_urls, 'urlpatterns', [])
panel_urlpatterns = urlpatterns
