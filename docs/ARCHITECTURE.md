# Arquitetura

## Visão geral

```
                    ┌──────────────────────────────────────────────┐
                    │              Cron no host Dokku              │
                    │  08:40 / 13:00 / 19:00 America/Sao_Paulo     │
                    └───────────────┬──────────────────────────────┘
                                    │ python manage.py sync_trackings
                                    ▼
   ┌────────────┐   HTTP + X-API-Key   ┌─────────────────┐
   │PacoteVício │ ◄────────────────────────►│ apps/carriers   │
   │   API      │    (1 request / package)  │ client+adapters │
   └────────────┘                           └────────┬─────────┘
                                                     │ NormalizedPayload
                                                     ▼
                              ┌─────────────────────────────────┐
                              │ apps/carriers/sync.py           │
                              │ dedupe via fingerprint, estados, │
                              │ atraso, cota, last_error/last_raw│
                              └───────────────┬─────────────────┘
                                              ▼
                              ┌─────────────────────────────────┐
                              │      PostgreSQL (prod)          │
                              │ Package / TrackingEvent / SyncLog│
                              └───────────────┬─────────────────┘
                                              ▼
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            Web UI (templates)              API DRF (/api/v1/)
            dashboard, timeline            Api-Key → Hermes agent
```

## Decisões de design

### 1. Padrão Adapter + normalização

Cada transportadora devolve um JSON **completamente diferente**. Um único módulo
`apps/carriers/adapters.py` concentra as 6 classes (`CorreiosAdapter`,
`AliExpressAdapter`, `ShopeeAdapter`, `AnjunAdapter`, `JTExpressAdapter`,
`TotalExpressAdapter`), todas herdando `BaseAdapter` e expondo a mesma interface:

- `.nid` — slug da transportadora (mesmo valor do `choices` do modelo).
- `.name`, `.host_path` (ex.: `/correios`).
- `.requires_document` — somente J&T exige o CPF do destinatário.
- `.build_params(tracking_code, document="")` — monta os query params da API.
- `.normalize(raw) -> NormalizedPayload` — converte a resposta bruta para o formato canônico.

O formato canônico (`apps/carriers/payload.py`):

```python
@dataclass
class NormalizedPayload:
    tracking_code: str
    status_code: str
    status_label: str
    location: str
    last_event_at: datetime | None
    estimated_delivery: date | None
    is_terminal: bool          # True = encomenda em estado final
    terminal_state: str | None # estado terminal canônico ("delivered") quando is_terminal
    events: list[EventData]    # EventData(occurred_at, status_key, status_label, location, raw)
    raw: dict                  # resposta original, para debug
```

`terminal_state` permite que cada adapter informe *qual* estado final a encomenda
atingiu (ex.: "delivered") de forma independente do nome cru do evento. Se nulo, o
`_apply_events` assume o default `delivered`.

### 2. Detecção automática de transportadora

Os códigos de rastreio têm formatos estáveis por transportadora; `detect_carrier(code)`
aplica regex em ordem fixa:

| Transportadora | Padrão |
|---|---|
| Correios | `^[A-Z]{2}\d{9}BR$` |
| AliExpress | `^(LP\d{9,}CN\|[A-Z]{2}\d{9,}CN)$` |
| Shopee | `^BR\d{12,}$` |
| Anjun | `^AJ\d{6,}$` (case-insensitive) |
| J&T | `^\d{10,18}$` |
| Total Express | `^[A-Z]{3,5}\d{6,}(?:[tx]{1,2})?$` |

Na web o usuário pode sobrescrever a transportadora manualmente; nos forms a detecção
valida o código antes de salvar. Tanto `forms.py` quanto a `api.py` usam o helper
`resolve_carrier(code, preferred)` — se `preferred` (carrier informado) existir, ele
vence; senão cai na detecção por regex. Um código que não bate em **nenhum** padrão só é
aceito com carrier manual se passar em `is_plausible_code` (dígitos, sem espaços, ≥6
caracteres) — evita rótulo digitado por engano no campo de código.

### 3. Parsing de datas

`apps/carriers/parsing.py` normaliza os vários formatos de data que os carriers enviam
(ISO com espaço, unix em ms/seg, `DD-MM-YYYY HH:MM:SS`, `DD/MM/YYYY`) para `datetime`
aware no fuso `America/Sao_Paulo`.

### 4. Sincronização (`apps/carriers/sync.py`)

O management command `sync_trackings` (cron) e o botão **"Atualizar todos"** do painel web
executam `sync_all()`, que itera apenas as encomendas `is_active=True` ainda **não
sincronizadas hoje** — `pending_packages()` filtra `last_synced_at` nulo ou anterior ao
início do dia (janela "no dia", para não consumir cota re-consultando o que já foi
sincronizado). Para cada uma, `sync_package()`:

1. Confere a **cota** (`SyncLog.is_paused()`) e devolve `SyncResult.PAUSED` se estourou.
2. Monta params via adapter (`document` do CPF se necessário — sem ele, J&T devolve
   `SyncResult.NO_DOCUMENT`).
3. `client.fetch(adapter.nid, tracking_code, document)`; registra `SyncLog.increment()` após sucesso.
4. `adapter.normalize(raw)` → `_apply_events()`:
   - cria eventos com **dedupe** via `make_fingerprint` (SHA1 de
     `package_id;occurred_at;status_key;status_label`) usando `bulk_create(ignore_conflicts=True)`.
   - atualiza `status_code/label`, `location`, `last_event_at`, `estimated_delivery`,
     `last_raw`, `last_error`.
   - se `is_terminal` → `terminal_state or "delivered"`, `mark_terminal()` (desativa a
     encomenda e limpa `last_raw` para não guardar payload pesado inútil).
   - se em trânsito e `estimated_delivery < hoje` → `is_delayed=True`.
5. Erros: **4xx permanente** (`400/404/410/422` — `PERMANENT_CLIENT_ERRORS`) desativa a
   encomenda (`is_active=False`) e retorna `SyncResult.ERROR`; `401/403` e 5xx/timeout
   apenas gravam `last_error` (retentativa no próximo cron).

Resultado tipado (`SyncResult`, enum em `sync.py`):

| Valor | Significado |
|---|---|
| `OK` | sincronizado com sucesso |
| `ERROR` | falha (5xx/timeout ou 4xx permanente) |
| `PAUSED` | cota mensal atingida |
| `NO_DOCUMENT` | sem CPF (J&T) — nada foi consultado |

**Paralelismo:** `sync_all()` consome as encomendas num `ThreadPoolExecutor` com
`SYNC_WORKERS` workers (default 4). A paralelização é desativada automaticamente sob
`SQLITE` (lock de escrita entre threads) e quando `SYNC_WORKERS=1`. O `client` reutiliza
uma única `requests.Session` (connection pooling + keep-alive) para todas as chamadas.

### 5. Estado final encerra a encomenda

Estados terminais (`TERMINAL_STATES`): `delivered`, `failed`, `returned`, `inactive`.
Assim que o rastreio chega em estado final (`is_terminal=True` no payload), a encomenda
vira `is_active=False` e sai da fila de sincronização do cron — economizando cota.

### 6. Cota mensal (PacoteVício)

`core.models.SyncLog` guarda o total de requisições do **mês** (linha única por mês,
`month` = primeiro dia do período). O campo `quota_limit` é inicializado com `COTA_MENSAL`
(default 1000) e o `is_paused()` mantém a execução abaixo do teto. Quando atinge o limite,
a sincronização pausa até o próximo período.

### 7. Campos `last_raw` e `last_error`

`Package.last_raw` guarda o último payload bruto (utilitário de debug) e `last_error` a
última falha — ambos visíveis na UI (badge de aviso) e no admin. Por serem pesados, o
`last_raw` é excluído das consultas de listagem (`.defer("last_raw")`) no dashboard web,
no admin via ORM e na API.

### 8. Sync manual (web) em background

O botão "Atualizar agora" do painel web (`package_sync_now`) não bloqueia a requisição:
ele despacha `spawn_background_sync()` — uma `threading.Thread` daemon que re-busca a
encomenda, executa `sync_package()` e fecha a conexão do Django no fim (`connection.close()`),
evitando vazamento de conexão entre threads. O botão **"Atualizar todos"** (`sync_all_now`,
`POST /sync/all/`) faz o mesmo com `spawn_background_sync_all()`, que roda `sync_all()`
apenas sobre as encomendas pendentes. O resultado aparece na próxima atualização
automática do dashboard (auto-refresh via partial). A API DRF (`POST .../sync/`) permanece
**síncrona** por contrato de consumo (`sync_status` na resposta).

## Modelo de dados

### `trackings.Package`

| Campo | Tipo | Observação |
|---|---|---|
| `tracking_code` | Char unique | código de rastreio |
| `carrier` | Char choices | slug da transportadora |
| `label` | Char | apelido amigável |
| `document` | Char (16) | CPF do destinatário, dígitos (J&T) |
| `status_code` / `status_label` | Char | último status cru / label |
| `location` | Char | local do último evento |
| `last_event_at` | DateTime | momento do último evento |
| `estimated_delivery` | Date | previsão de entrega |
| `state` | Char choices | in_transit / delivered / failed / returned / inactive |
| `is_active` | Bool | participa do cron? |
| `is_delayed` | Bool | flag persistido do atraso (usado por notificações) |
| `is_overdue` | property | cálculo em tempo real: `in_transit` E `estimated_delivery` passou — fonte única para a UI marcar "Atrasada" |
| `last_synced_at` | DateTime | última sincronização |
| `last_error` / `last_raw` | Text / JSON | diagnóstico |
| `created_at` / `updated_at` | DateTime | auditoria |

### `trackings.TrackingEvent`

`package` FK (related `events`), `occurred_at`, `status_key`, `status_label`,
`location`, `raw` (JSON), `fingerprint` (SHA1, unique para dedupe), `created_at`.

### `core.SyncLog`

`month` (unique), `requests`, `quota_limit`, `created_at`. Métodos `increment()`,
`count_period()`, `is_paused()`.

## API externa

A API PacoteVício é consumida em `apps/carriers/client.py` (`PacoteVicioClient.fetch`),
que injeta o header `X-API-Key` e respeita `PACOTE_VICIO_BASE_URL` +
`PACOTE_VICIO_TIMEOUT`. As respostas de exemplo usadas nos testes das transportadoras
estão em `apps/carriers/tests/fixtures/*.json` (extraídas do `doc_api.md`).