# Compatibility shim for tests that import config.urls_website
from django.http import HttpResponse
from django.views.static import serve
from config import urls as _urls

# Public media serve: allow only certain public prefixes (e.g., adarshimg/)
PUBLIC_PREFIXES = ('adarshimg/',)

def _normalize_media_path(raw_path):
    parts = []
    for part in str(raw_path or '').replace('\\', '/').split('/'):
        part = part.strip()
        if not part or part == '.':
            continue
        if part == '..':
            return ''
        parts.append(part)
    return '/'.join(parts)


def _public_media_serve(request, path, document_root=None):
    rel_path = _normalize_media_path(path)
    if not rel_path:
        return HttpResponse(status=404)
    if any(rel_path.startswith(p) for p in PUBLIC_PREFIXES):
        # Delegate to Django's static file serving which raises Http404 for missing files
        return serve(request, rel_path, document_root=document_root)
    return HttpResponse(status=404)

urlpatterns = getattr(_urls, 'urlpatterns', [])
website_urlpatterns = urlpatterns
