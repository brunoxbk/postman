# API — Consumo pelo Hermes agent

API REST sob `/api/v1/`, protegida por **chave de API** (`djangorestframework-api-key`).
Todo endpoint exige o cabeçalho:

```
Authorization: Api-Key <CHAVE>
```

## Gerar a chave

Pelo admin (App API keys) ou pelo shell:

```bash
dokku run postman python manage.py shell -c "
from rest_framework_api_key.models import APIKey
k, key = APIKey.objects.create_key(name='hermes-agent')
print(key)   # mostra a chave uma única vez
"
```

Salve a chave retornada. Ela não pode ser recuperada depois.

## Endpoints

### `GET /api/v1/health/`

Retorna o status do serviço (usado por hooks de deploy e monitors).

```
curl -H "Authorization: Api-Key $KEY" https://postman.example.com/api/v1/health/
```

```json
{ "status": "ok" }
```

### `GET /api/v1/packages/`

Lista encomendas. Filtros opcionais: `q` (código, `icontains`), `carrier`, `state`.

```
curl -H "Authorization: Api-Key $KEY" \
  "https://postman.example.com/api/v1/packages/?state=in_transit&carrier=anjun"
```

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "tracking_code": "AM101610575BR",
      "carrier": "correios",
      "carrier_display": "Correios",
      "label": "Na casa da mãe",
      "status_code": "E",
      "status_label": "ENTREGUE",
      "location": "Recife / PE",
      "last_event_at": "2025-03-04T02:30:03-03:00",
      "estimated_delivery": "2025-03-20",
      "state": "delivered",
      "is_active": false,
      "is_delayed": false,
      "last_synced_at": "2025-03-04T02:30:00-03:00",
      "last_error": "",
      "created_at": "2025-03-01T10:00:00-03:00",
      "events": [
        {
          "occurred_at": "2025-03-04T02:30:03-03:00",
          "status_key": "BDE",
          "status_label": "ENTREGUE",
          "location": "Recife / PE",
          "raw": { "...": "payload original" }
        }
      ]
    }
  ]
}
```

### `GET /api/v1/packages/{tracking_code}/`

Detalhe de uma encomenda pelo código (URL-encode se necessário).

```
curl -H "Authorization: Api-Key $KEY" \
  https://postman.example.com/api/v1/packages/AM101610575BR/
```

### `POST /api/v1/packages/`

Cadastra uma encomenda para rastreamento.

- `tracking_code` (obrigatório, único)
- `carrier` (opcional — se omitido, fica vazio e a detecção automática roda no próximo
  sync; na web o form detecta na hora)
- `label` (opcional)
- `document` (opcional; **obrigatório para J&T** — CPF do destinatário, só dígitos)

```
curl -s -X POST https://postman.example.com/api/v1/packages/ \
  -H "Authorization: Api-Key $KEY" \
  -H "Content-Type: application/json" \
  -d '{"tracking_code":"AJ250101341570001","carrier":"anjun","label":"Pedido Shopee"}'
```

Resposta `201` com o objeto criado (mesmo shape do GET). Código duplicado → `400`.

### Outros métodos

O `ModelViewSet` também aceita `PUT/PATCH/DELETE` em `/packages/{tracking_code}/`
(para correção/manutenção), tudo protegido pela mesma chave.

## Erros

| Código | Quando |
|---|---|
| 401 | chave ausente ou inválida (cabeçalho `WWW-Authenticate: Api-Key`) |
| 400 | payload inválido (código duplicado, transportadora desconhecida) |
| 404 | código inexistente |

Exemplo de erro:

```json
{ "tracking_code": ["Código já cadastrado."] }
```