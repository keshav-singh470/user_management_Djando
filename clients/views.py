from rest_framework import status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Client
from .serializers import ClientSerializer


class ClientPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class ClientViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Clients with Pagination and Authentication.
    - List clients (paginated, e.g. /api/clients/?page=1&page_size=10)
    - Create client (POST /api/clients/)
    - Retrieve client (GET /api/clients/<id>/)
    - Update client (PUT / PATCH /api/clients/<id>/)
    - Delete client (DELETE /api/clients/<id>/ -> soft delete sets is_active=False)
      (Pass ?hard=true to permanently delete)
    """
    queryset = Client.objects.all().order_by('-id')
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ClientPagination

    def destroy(self, request, *args, **kwargs):
        client = self.get_object()
        if request.query_params.get('hard') == 'true':
            client.delete()
            return Response({'message': 'Client deleted permanently'}, status=status.HTTP_200_OK)
        client.is_active = False
        client.save()
        return Response({'message': 'Client deactivated successfully (soft delete)'}, status=status.HTTP_200_OK)
