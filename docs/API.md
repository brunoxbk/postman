# API — Consumo pelo Hermes agent

API REST sob `/api/v1/`, protegida por **chave de API** (`djangorestframework-api-key`).
Todo endpoint exige o cabeçalho, **exceto** `GET /health/` e `GET /schema/` (públicos):

```
Authorization: Api-Key <CHAVE>
```

> **Implementação:** como o pacote removeu a classe de autenticação nativa na v3.1, a
> aplicação usa a classe customizada `apps/trackings.auth.APIKeyAuthentication`
> (`REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES`). Na prática o comportamento é o
> mesmo: o header acima é validado e, se ausente/inválido, a resposta é **401** com o
> cabeçalho `WWW-Authenticate: Api-Key`.

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

Retorna o status do serviço (usado por hooks de deploy e monitors). **Público — não exige
chave.**

```
curl https://postman.example.com/api/v1/health/
```

```json
{ "status": "ok" }
```

### `GET /api/v1/schema/`

Schema OpenAPI 3.0 da API, também público. Serve como fonte única para integrar o Hermes
agent (endpoints, parâmetros, auth).

### `GET /api/v1/packages/`

Lista encomendas. Filtros opcionais: `q` (código, `icontains`), `carrier`, `state`.

```
curl -H "Authorization: Api-Key $KEY" \
  "https://postman.example.com/api/v1/packages/?state=in_transit&carrier=anjun"
```

> A listagem é **paginada**: a resposta é `{ "count", "next", "previous", "results" }`.
> Use `?limit=` e `?offset=` para navegar (padrão `limit=50`).

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
          "location": "Recife / PE"
        }
      ]
    }
  ]
}
```

> **Privacidade:** os eventos retornados **não incluem o campo `raw`** (payloads das
> transportadoras podem conter nome do destinatário, telefone e endereço). O payload
> bruto fica disponível apenas no admin e no painel web (debug).
>
> **Desempenho:** na listagem, `events` traz apenas um **preview dos 50 eventos mais
> recentes** (entre todas as encomendas da página); no detalhe (`/packages/{código}/`)
> os eventos vêm completos. O campo pesado `last_raw` não é selecionado na listagem.

### `GET /api/v1/packages/{tracking_code}/`

Detalhe de uma encomenda pelo código (URL-encode se necessário).

```
curl -H "Authorization: Api-Key $KEY" \
  https://postman.example.com/api/v1/packages/AM101610575BR/
```

### `POST /api/v1/packages/`

Cadastra uma encomenda para rastreamento.

- `tracking_code` (obrigatório, único)
- `carrier` (opcional — **se omitido, o carrier é detectado automaticamente** pelo código
  salvo; `400` se o código não for reconhecido e nenhum carrier for informado)
- `label` (opcional)
- `document` (opcional, **write-only** — não retorna na resposta; **obrigatório para J&T** —
  CPF do destinatário, só dígitos)

```
curl -s -X POST https://postman.example.com/api/v1/packages/ \
  -H "Authorization: Api-Key $KEY" \
  -H "Content-Type: application/json" \
  -d '{"tracking_code":"AJ250101341570001","carrier":"anjun","label":"Pedido Shopee"}'
```

Resposta `201` com o objeto criado (mesmo shape do GET). Código duplicado → `400`.
Detecção automática: omita o `carrier` — `{"tracking_code":"AM101610575BR"}` cria com
`carrier="correios"`.

> O `tracking_code` é **normalizado para MAIÚSCULAS** e a duplicidade é verificada
> sem diferenciar maiúsculas/minúsculas (ex.: `am101610575br` e `AM101610575BR`
> são o mesmo código).

### `POST /api/v1/packages/{tracking_code}/sync/`

Executa um sync imediato da encomenda (consome 1 requisição da cota diária). Retorna o
status do sync e o pacote atualizado.

```
curl -s -X POST https://postman.example.com/api/v1/packages/AM101610575BR/sync/ \
  -H "Authorization: Api-Key $KEY"
```

```json
{
  "sync_status": true,
  "package": { "...": "mesmo shape do GET" }
}
```

Valores de `sync_status`: `true` (ok), `false` (erro controlado, exemplo: J&T sem CPF ou
erro permanente 4xx), `null` (cota diária atingida — sincronização pausada).

> **Erro permanente (4xx):** códigos `400`, `404`, `410` e `422` fazem a encomenda ser
> **desativada** (`is_active=false`) — ela sai da fila do cron e só volta via "Reabrir
> rastreio" (admin ou painel web). Códigos como `401`/`403` não desativam.

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