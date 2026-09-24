# 📦 API PacoteVício (v1) — Rastreamento de Encomendas

Integração da aplicação com a API pública de rastreamento PacoteVício
(`https://api.pacotevicio.dev`). Uma única rota normalizada consulta a transportadora e
devolve o histórico do objeto, com detecção automática da transportadora pelo formato do
código.

> O contrato completo está documentado em `pacote_vicio.md` na raiz do repositório
> (versão formatada do manual oficial).

## 🔗 Acesso à API

| Item | Valor |
|---|---|
| Base URL | `https://api.pacotevicio.dev` |
| Versionamento | todos os endpoints ficam sob `/v1` |
| Autenticação | header `X-API-Key` (formato `pv1_...`) |
| Formato | JSON; erros nunca chegam com status 2xx |

Headers:

| Header | Obrigatório | Valor |
|---|---|---|
| `X-API-Key` | Sim | Chave no formato `pv1_...` |
| `X-Tracking-Document` | Depende | CPF/CNPJ (somente dígitos) — **obrigatório para J&T Express** |
| `User-Agent` | Recomendado | Identificador da aplicação, ex.: `postman/1.0` |

## 🛠️ Como Utilizar

### 1. Obter uma chave

Gere a chave no portal da PacoteVício (página **Chaves de API**). Ela é consumida pelas
variáveis do app:

```
PACOTE_VICIO_API_KEY=pv1_...
PACOTE_VICIO_BASE_URL=https://api.pacotevicio.dev
PACOTE_VICIO_TIMEOUT=35
PACOTE_VICIO_RETRY_LEVEL=high
PACOTE_VICIO_USER_AGENT=postman/1.0
```

### 2. Rastrear um objeto

O app usa a rota com transportadora forçada (determinística e mais rápida):

```
GET /v1/track/{courier}/{tracking_code}
```

```bash
curl "https://api.pacotevicio.dev/v1/track/correios/AM101610575BR?retry_level=high" \
  -H "X-API-Key: pv1_..." \
  -H "User-Agent: postman/1.0"

curl "https://api.pacotevicio.dev/v1/track/jtexpress/888030556767025" \
  -H "X-API-Key: pv1_..." \
  -H "X-Tracking-Document: 12345678901"
```

`retry_level` controla quanta latência a API tolera antes de desistir (`low` 10s, `medium` 20s,
`high` 45s). Para o job em segundo plano (cron e botão de sync) o padrão é `high`.

### 3. Resposta normalizada

```json
{
  "tracking_code": "BR123456789BR",
  "courier": "correios",
  "status": "delivered",
  "status_updated_at": "2026-07-20T10:00:00Z",
  "service": "SEDEX",
  "origin": null,
  "destination": { "country": "BR", "state": "SP", "city": "Franca", "name": null },
  "estimated_delivery_date": "2026-07-20",
  "delivered_at": "2026-07-20T10:00:00Z",
  "recipient": { "name": "Bruno", "signed_by": "BRUNO" },
  "events": [
    {
      "timestamp": "2026-07-14T18:51:28Z",
      "status": "unknown",
      "description": "Rastreio fornecido por PacoteVicio.dev",
      "location": null,
      "courier_status_code": null,
      "courier_status_label": null,
      "detail": null,
      "comment": null
    },
    {
      "timestamp": "2026-07-20T10:00:00Z",
      "status": "delivered",
      "description": "Objeto entregue ao destinatário",
      "location": { "country": "BR", "state": "SP", "city": "Franca", "facility": null },
      "courier_status_code": "BDE",
      "courier_status_label": "Entregue",
      "detail": null,
      "comment": null
    }
  ]
}
```

Regras que o app respeita:

- **Use `status`, nunca `courier_status_code`** — o primeiro é normalizado e estável; o segundo
  é o vocabulário bruto da transportadora e pode mudar sem aviso.
- **`events` vai do mais antigo para o mais recente**; o evento atual é o último do array.
- No plano Básico o **primeiro evento é uma atribuição sintética** (`status: unknown`,
  "Rastreio fornecido por PacoteVício.dev"). É **proibido remover, ocultar, alterar ou
  substituir** esse evento — o app o preserva na timeline.
- **Timestamps são RFC 3339 em UTC** (sufixo `Z`).
- `estimated_delivery_date` é `YYYY-MM-DD`, sem fuso.

### Status normalizados

| `status` | Significado |
|---|---|
| `pending` | Etiqueta emitida, ainda sem movimentação |
| `collected` | Coletado do remetente ou postado |
| `in_transit` | Em trânsito pela rede da transportadora |
| `out_for_delivery` | Com o entregador, saiu para entrega |
| `available_for_pickup` | Aguardando retirada em um ponto |
| `tax` | Aguardando pagamento de tributo ou revisão tributária |
| `delivered` | Entregue (**terminal** — encerra o rastreio) |
| `exception` | Tentativa falha, problema aduaneiro, avaria ou endereço |
| `returned` | Devolvido ao remetente (**terminal** — encerra o rastreio) |
| `unknown` | Sem tradução, ou atribuição sintética do plano Básico |

Valores desconhecidos devem ser tratados como `unknown`.

### Erros

Use **`error.code`** (contrato estável), nunca a `message`. Envelope:

```json
{
  "error": {
    "code": "tracking_not_found",
    "message": "A transportadora não encontrou registro para este código.",
    "request_id": "0ebcea5b-1727-4bf9-af88-4deb11b438f2"
  }
}
```

Códigos relevantes para o app:

| Código | HTTP | Tratamento no app |
|---|---|---|
| `invalid_api_key`, `missing_api_key` | 401 | mantém o pacote ativo (log; a chave pode ser corrigida) |
| `subscription_inactive`, `account_suspended`, `phone_verification_required` | 403 | mantém o pacote ativo (log) |
| `tracking_not_found` | 404 | mantém o pacote ativo — o código **pode** passar a existir depois; consome cota |
| `invalid_tracking_code`, `courier_not_supported` | 400 | **desativa** o pacote (não adianta repetir) |
| `courier_not_detected`, `document_required`, `invalid_document` | 422 | mantém o pacote ativo (log) |
| `rate_limit_exceeded` | 429 | espera o `Retry-After` e repete uma vez |
| `quota_exceeded` | 429 | mantém ativo; erro de cota do período |
| `courier_unavailable`, `courier_timeout`, `service_unavailable`, 5xx | 502/504/5xx | falha temporária — repetir mais tarde; não consome cota |

Cobrança: consome cota apenas quando a transportadora dá resposta definitiva — `200` e
`404 tracking_not_found`. As demais (401/403/400/422/429/5xx) não consomem.

## 💻 Endpoints disponíveis

| Transportadora | slug (`courier`) | Headers obrigatórios |
|---|---|---|
| Correios | `correios` | — |
| AliExpress | `aliexpress` | — |
| Shopee Xpress | `shopee` | — |
| Anjun Express | `anjun` | — |
| J&T Express | `jtexpress` | `X-Tracking-Document` (CPF 11 ou CNPJ 14) |
| Total Express | `totalexpress` | — |

O catálogo autoritativo pode ser consultado em:

```
GET /v1/couriers
```

## 🐍 No código

- `apps/carriers/client.py` — chamadas HTTP (URL v1, headers, retry e envelope de erro).
- `apps/carriers/adapters.py` — `normalize_v1` (resposta normalizada → `NormalizedPayload`,
  mapeamento de status terminais), detecção de transportadora e `is_plausible_code`.
- `apps/carriers/parsing.py` — parse de RFC 3339 em UTC (sufixo `Z`, offsets e sem fuso).
- `apps/carriers/sync.py` — fluxo `sync_package`/`sync_all` com decisão por `error.code`.