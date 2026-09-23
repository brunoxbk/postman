from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

SCHEMA = {
    "openapi": "3.0.3",
    "info": {
        "title": "Rastreador de Encomendas API",
        "description": "API do painel de rastreio (PacoteVício). Autenticação Bearer via "
                       "header `Authorization: Api-Key <CHAVE>`.",
        "version": "1.0.0",
    },
    "paths": {
        "/api/v1/health/": {
            "get": {"summary": "Healthcheck público", "security": [], "responses": {"200": {"description": "ok"}}}
        },
        "/api/v1/packages/": {
            "get": {
                "summary": "Lista encomendas",
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}, "description": "Código (icontains)"},
                    {"name": "carrier", "in": "query", "schema": {"type": "string"}},
                    {"name": "state", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "Lista paginada"}},
            },
            "post": {
                "summary": "Cadastra encomenda (carrier auto-detectado se omitido)",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["tracking_code"],
                                "properties": {
                                    "tracking_code": {"type": "string"},
                                    "carrier": {"type": "string"},
                                    "label": {"type": "string"},
                                    "document": {"type": "string", "description": "CPF só dígitos (J&T)"},
                                },
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Criado"}, "400": {"description": "Payload inválido"}},
            },
        },
        "/api/v1/packages/{tracking_code}/": {
            "get": {"summary": "Detalhe da encomenda", "parameters": [{"name": "tracking_code", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Encomenda"}}},
            "patch": {"summary": "Altera parcialmente a encomenda", "parameters": [{"name": "tracking_code", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Atualizada"}}},
            "delete": {"summary": "Remove a encomenda", "parameters": [{"name": "tracking_code", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"204": {"description": "Removida"}}},
        },
        "/api/v1/packages/{tracking_code}/sync/": {
            "post": {
                "summary": "Executa sync imediato (consome 1 requisição da cota)",
                "parameters": [{"name": "tracking_code", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "sync_status + pacote atualizado"}},
            }
        },
    },
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "Authorization", "description": "Api-Key <CHAVE>"}
        }
    },
    "security": [{"ApiKeyAuth": []}],
}


class SchemaView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return JsonResponse(SCHEMA)