from django.http import JsonResponse
from django.conf import settings
from django.db.models import Count, OuterRef, Subquery, IntegerField
from django.db.models.functions import Coalesce
from organisation.models import Organisation
from tables.models import IDCard

def api_public_clients_list(request):
    """
    Expose a list of all client profiles with their names, emails,
    and total count of cards across all tables.
    
    Protected by server-to-server API Key (X-API-KEY header or query param).
    """
    # Accept header first, fallback to query param
    provided_key = request.META.get('HTTP_X_API_KEY') or request.GET.get('api_key', '')
    expected_key = getattr(settings, 'WEB_APP_API_KEY', '')

    if not expected_key or provided_key != expected_key:
        return JsonResponse({
            'success': False,
            'message': 'Unauthorized. A valid X-API-KEY is required.'
        }, status=401)

    # Subquery to aggregate card counts across all tables for each client
    card_count_subquery = IDCard.objects.filter(
        table__group__client=OuterRef('pk')
    ).values('table__group__client').annotate(
        count=Count('id')
    ).values('count')

    # Fetch clients, prefetch their user profile for email lookup
    clients_queryset = Organisation.objects.select_related('user').annotate(
        total_records_count=Coalesce(Subquery(card_count_subquery, output_field=IntegerField()), 0)
    ).order_by('name')

    clients_data = []
    for client in clients_queryset:
        clients_data.append({
            'name': Organisation.name,
            'email': Organisation.user.email if client.user else '',
            'total_records': Organisation.total_records_count,
        })

    return JsonResponse({
        'success': True,
        'clients': clients_data
    })
