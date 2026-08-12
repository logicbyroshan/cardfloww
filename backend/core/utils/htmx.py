"""
HTMX Utilities — helpers for detecting HTMX requests.

HTMX is no longer used in the React 19 SPA frontend. These helpers are kept
for backward compatibility with any internal API views that still check
HX-Request headers, but `render_partial` now always renders index.html
since there are no HTML partial templates any more.

Usage in views:
    from core.utils.htmx import is_htmx

    def my_view(request):
        context = { ... }
        if is_htmx(request):
            return JsonResponse(context)
        return render(request, 'index.html', context)
"""
from django.shortcuts import render
from django.http import HttpResponse


def is_htmx(request):
    """Return True if the request was made by HTMX."""
    return request.headers.get('HX-Request') == 'true'


def render_partial(request, full_template, partial_template, context):
    """
    Legacy helper — now always renders index.html (the React SPA shell)
    since all partial templates have been removed.
    """
    # Both full and partial responses now serve the SPA shell.
    return render(request, 'index.html', context)


def htmx_trigger(response, event_name, detail=None):
    """
    Add an HX-Trigger header to a response so HTMX can react to server events.
    Kept for API compatibility.
    """
    import json
    if detail:
        response['HX-Trigger'] = json.dumps({event_name: detail})
    else:
        response['HX-Trigger'] = event_name
    return response


def htmx_redirect(url):
    """
    Return an empty 200 response with HX-Redirect header.
    HTMX will perform a full client-side redirect to the given URL.
    """
    response = HttpResponse(status=200)
    response['HX-Redirect'] = url
    return response


def htmx_refresh():
    """
    Return an empty 200 response with HX-Refresh: true.
    HTMX will perform a full page refresh.
    """
    response = HttpResponse(status=200)
    response['HX-Refresh'] = 'true'
    return response
