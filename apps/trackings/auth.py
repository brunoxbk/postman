from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_api_key.models import APIKey
from rest_framework_api_key.permissions import KeyParser


class APIKeyAuthentication(BaseAuthentication):
    key_parser = KeyParser()

    def authenticate_header(self, request):
        return "Api-Key"

    def authenticate(self, request):
        key = self.key_parser.get(request)
        if not key:
            raise AuthenticationFailed("Chave de API ausente.")
        if not APIKey.objects.is_valid(key):
            raise AuthenticationFailed("Chave de API inválida.")
        return (None, key)