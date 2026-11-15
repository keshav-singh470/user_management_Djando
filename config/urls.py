from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
import re
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def custom_404(request, exception=None):
    parts = request.path.strip('/').split('/')
    bad = [p for p in parts if p.lower() in ('null', 'undefined', 'none', 'nan')]
    if bad:
        hint = (f"The URL contains '{bad[0]}', which is not a valid id. "
                "Replace it with a real number, for example /api/profiles/5/.")
    elif any('=' in p for p in parts):
        hint = ("Query parameters must come after a '?', not inside the path. "
                "Example: /api/projects/?is_active=false")
    elif any(re.fullmatch(r'-?\d+\.\d+', p) for p in parts):
        hint = "Ids must be whole numbers like 5, not decimals like 2.5."
    elif not request.path.endswith('/'):
        hint = f"URLs in this API end with a slash. Try: {request.path}/"
    else:
        hint = ("Check the spelling of the URL. If it contains an id, the id must be a "
                "whole number, for example /api/profiles/5/.")
    return JsonResponse({'success': False, 'status_code': 404,
                         'message': 'The URL you called does not exist.',
                         'hint': hint, 'path': request.path}, status=404)


def custom_500(request):
    return JsonResponse({'success': False, 'status_code': 500,
                         'message': 'Something went wrong on the server.',
                         'hint': 'Please try again. If it keeps happening, contact the developer.'},
                        status=500)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema')),
    path('api/', include('users.urls')),
    re_path(r'^api/.*$', custom_404),      # sabse last: DEBUG=True mein bhi JSON 404
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = custom_404
handler500 = custom_500