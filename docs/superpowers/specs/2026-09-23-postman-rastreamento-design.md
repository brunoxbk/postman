# Design — Postman: Rastreador de Encomendas (Django + API)

**Data:** 2026-09-23
**Status:** Aprovado pelo usuário em 2026-09-23 (fluxo de aprovação por seção)
**Escopo:** Aplicação Django com painel web e API consumindo a API PacoteVício (RapidAPI).

---

## 1. Visão geral (dado na Seção 1 do brainstorm)

Aplicação pessoal para cadastrar encomendas de **6 transportadoras** (Correios, AliExpress,
Shopee Xpress, Anjun Express, J&T Express, Total Express) e acompanhar o timetrack
(histórico de eventos) em um painel simples e amigável, com sincronização automática
**3×/dia via cron** e uma **API protegida** para consumo por um Hermes agent.

Fonte dos dados: API **PacoteVício** descrita em `doc_api.md` (RapidAPI, plano grátis
~1.000 req/mês).

### Stack

- **Python 3.12** · **Django 5.2 (LTS)** · **Django REST Framework**
- **PostgreSQL** (plugin `dokku-postgres`)
- **django-environ** — toda configuração desacoplada via variáveis de ambiente
- **djangorestframework-api-key** — chave `Api-Key` para o Hermes agent
- **WhiteNoise** — estáticos em produção
- **requests** — cliente HTTP para a API externa (timeout 35s, `confidence_level=high`)
- **Gunicorn** — servidor (via `Procfile`/Dokku)

### Estrutura do projeto

```
postman/
├── config/                 # settings (base/dev/prod), urls, wsgi/asgi
├── apps/
│   ├── core/               # templates base, utils, admin
│   ├── carriers/           # adapters por transportadora + detecção + sync
│   └── trackings/          # modelos Encomenda/Evento, views web, serializers/API
├── docs/
│   ├── ARCHITECTURE.md     # visão de arquitetura
│   ├── API.md              # API para o Hermes agent
│   ├── DEPLOY.md           # deploy no Dokku (incl. cron)
│   └── superpowers/specs/  # este documento
├── .env.sample
├── .env.example
├── Procfile
├── Dokkufile (ou .dockerignore + Procfile)
└── requirements.txt
```

## 2. Modelo de dados (Seção 2 do brainstorm)

### `Carrier` (modelo/choices)

Mantido como *choices* Django (slug + nome), pois o cliente de cada transportadora é o
adapter correspondente. Evita tabela desnecessária.

| campo | tipo |
|---|---|
| slug | `correios` \| `aliexpress` \| `shopee` \| `anjun` \| `jtexpress` \| `totalexpress` |

### `Package` (Encomenda)

| campo | tipo | regras |
|---|---|---|
| tracking_code | Char(64, unique, index) | código de rastreio |
| carrier | choices | transportadora (detectada ou manual) |
| label | Char(128, blank) | nome amigável dado pelo usuário |
| document | Char(16, blank) | CPF somente dígitos — obrigatório p/ J&T, mascarado na UI |
| status_code | Char(32, blank) | último código de status (formato do carrier) |
| status_label | Char(255, blank) | último status legível (normalizado pt-BR) |
| location | Char(255, blank) | última localização (cidade/UF) |
| last_event_at | DateTime(null) | data do último evento |
| estimated_delivery | Date(null) | previsão de entrega |
| state | Char(20, default `in_transit`, indexed) | `in_transit` \| `delivered` \| `failed` \| `returned` \| `inactive` |
| is_active | Boolean(default True) | encerrado (estado final) → não consultado +\| visível |
| is_delayed | Boolean(default False) | computado por `sync` (previsão passou sem entregar) |
| last_synced_at | DateTime(null) | última sincronização |
| last_error | Text(blank) | último erro da API (4xx/5xx/timeout) |
| last_raw | JSONField(blank, default=dict) | payload bruto mais recente (debug) |
| created_at / updated_at | auto | — |
| [Meta de conformidade] | — | `constraints` único (tracking_code) |

### `TrackingEvent` (Evento)

| campo | tipo | regras |
|---|---|---|
| package | FK (related_name=`events`) | — |
| occurred_at | DateTime | data/hora do evento (normalizada) |
| status_key | Char(128) | código canônico do evento (ex `BDE`, `DELIVERED`) |
| status_label | Char(255) | descrição legível (pt-BR) |
| location | Char(255, blank) | `"Recife / PE"` quando disponível |
| raw | JSONField(blank, default=dict) | payload original |
| fingerprint | Char(256, unique) | hash dedupe: SHA1(`package_id;occurred_at;status_key;status_label`) |

Regra de negócio: **dedupe por fingerprint** — evita eventos duplicados entre syncs.

## 3. Regras de negócio (Seção 2/3)

1. **Ciclo de vida da encomenda:**
   - Estados: `in_transit` → `delivered` \| `returned` \| `failed` \| `inactive`
   - Quando o carrier reporta um **status final** (normalizado via adapter: Correios
     `finalizador=S`/`situacao=E`, AliExpress `Delivered`, Shopee `Delivered`, Anjun
     `signed`, J&T código 100, Total Express `ENTREGA REALIZADA`):
     `is_active=False`, `state` atualizado. Não volta a ser consultada (economia de cota).
2. **Atraso:** se `estimated_delivery < today` e `state != delivered` → `is_delayed=True`.
3. **Dedupe de eventos:** via `fingerprint` (ver modelo).
4. **Erros da API externa:** 4xx → registra `last_error` e **não retenta na mesma execução**;
   5xx/timeout → registra erro e retenta no próximo cron (com jitter). Nunca quebra a
   execução do lote (try/except por encomenda).
5. **Cota mensal (RapidAPI ~1.000 req/mês):** contador de requisições em
   `core.models.SyncLog`; se ultrapassar `COTA_MENSAL` (default 900), o cron **pausa**
   novas consultas e emite aviso no `manage.py check --deploy`/log + flag no dashboard.
6. **J&T exige `document` (CPF):** validação de 11 dígitos. Exibição mascarada na UI
   (somente últimos 2 dígitos). Sem `document`, encomenda J&T não é sincronizada
   (marcada `last_error` amigável).
7. **Detecção automática de transportadora** via máscara do código (ver adiante);
   usuário pode sobrepor manualmente no cadastro.

### Detecção automática

| transportadora | máscara |
|---|---|
| Correios | `^([A-Z]{2}\d{9}BR)$` |
| AliExpress | `^(LP\d{10,}CN\|...\|[A-Z]{2}\d{12,})$` (prefixos LP/SP/YY + CN) |
| Shopee | `^BR\d{13,}$` (ex `BR2561249217932`) |
| Anjun | `^AJ\d{12,18}$` |
| J&T | `^\d{10,20}$` (ou códigos `JT...`) |
| Total Express | `^[A-Z]{4}\d{4,}[tx]?$` (ex `AMZB901884819tx`) |

## 4. Integração com a API PacoteVício (Seção 3)

**Cliente HTTP:** uma classe `PacoteVicioClient` (httpx/requests) com timeout 35s e
cabeçalho `X-RapidAPI-Key`. Base URL e chave lidas do `.env`
(`PACOTE_VICIO_API_KEY`, `PACOTE_VICIO_BASE_URL`).

**Adapters (`apps/carriers/adapters/`):** cada transportadora implementa:

```python
class CarrierAdapter(ABC):
    nid = "correios"
    host_path = "/correios"
    def fetch_payload(self, package) -> dict       # request pronta p/ transportadora
    def normalize(self, raw) -> NormalizedPayload   # converte p/ canônico
    def is_terminal(self, raw/normalized) -> bool   # estado final?
    def extract_delivery_date(...) 
```

`NormalizedPayload` (dataclass): `events: list[EventData]`, `status_label`,
`status_code`, `location`, `last_event_at`, `estimated_delivery`, `is_terminal`.

Mapping de respostas divergentes (doc_api.md):

- **Correios:** `eventos[]`, `dtPrevista`, `situacao`, `finalizador`.
- **AliExpress:** `detailList[]`, `globalEtaInfo`, `status`.
- **Shopee:** `tracking_list[]`, `current_status`, `status_list`.
- **Anjun:** `nodeDataList[]`, `lastTrackStatus`.
- **J&T:** `details[]`, `keyword`; envia `document` no request.
- **Total Express:** `data.encomenda` + `data.layouts[].etapas[].listaStatus[]`.

## 5. Web UI (Seção 4)

Painel simples e amigável em **pt-BR**, templates Django + HTMX leve:

- **Login** (adm único, `createsuperuser`).
- **Dashboard (`/`):** cards de resumo (em trânsito / entregues / atrasadas), tabela de
  encomendas com última atualização em destaque, buscador, filtro por transportadora,
  botão "atualizar agora".
- **Detalhe (`/packages/<code>/`):** banner de status atual, previsão/atraso,
  **timeline vertical** de eventos + toggle para ver JSON bruto.
- **Cadastro (`/packages/new/`):** campo código (auto-detecta transportadora), override,
  label amigável, CPF quando J&T, nota.
- **Edição/ativação/exclusão** de encomendas.
- **Admin Django** para supervisão.

## 6. API para o Hermes agent (Seção 3)

DRF sob `/api/v1/`, protegida por **chave de API**
(`djangorestframework-api-key`, token `Authorization: Api-Key <chave>`), criada no Admin.

Endpoints:
- `GET  /api/v1/packages/` — listar (filtros: `q` código/estado, `carrier`, `state`)
- `POST /api/v1/packages/` — cadastrar (`tracking_code`, `carrier?`, `label?`, `document?`)
- `GET  /api/v1/packages/{tracking_code}/` — detalhe + eventos
- `GET  /api/v1/health/` — status do serviço (p/ Dokku e monitors)

Respostas em pt-BR normalizadas. Toda a doc em `docs/API.md` com exemplos cURL.

## 7. Seed/Computações & Cron (Seção 4)

Management command `sync_trackings`:

1. Seleciona encomendas `is_active=True` (e não encerradas).
2. Para cada uma: busca na API via adapter, normaliza, `update_or_create` eventos
   (dedupe), atualiza `status/estimated/is_delayed/state/is_active`.
3. Trata erros por item; registra `SyncLog`.
4. **Pausa cota** se próximo do limite mensal.

**Cron no host Dokku** (3×/dia — 08:40, 13:00, 19:00 America/Sao_Paulo):

```cron
40 8 * * * dokku run postman python manage.py sync_trackings
0 13 * * * dokku run postman python manage.py sync_trackings
0 19 * * * dokku run postman python manage.py sync_trackings
```

(Alternativa documentada: plugin `dokku-scheduler` / systemd timer.)

## 8. Deploy no Dokku (Seção 5)

- Build: `Procfile` (`web: gunicorn config.wsgi`) + `.dockerignore`; ou `Dockerfile`.
- Plugins: `dokku postgres:create`, `dokku postgres:link`.
- Variáveis: `DJANGO_SECRET_KEY`, `DJANGO_SETTINGS_MODULE=config.settings.prod`,
  `DJANGO_ALLOWED_HOSTS`, `PACOTE_VICIO_API_KEY`, `PACOTE_VICIO_BASE_URL`,
  `DATABASE_URL`, `COTA_MENSAL`, `DJANGO_DEBUG=0`.
- Passos em `docs/DEPLOY.md` (create app, push, `dokku run python manage.py migrate`,
  `createsuperuser`, letsencrypt, cron host-side).

## 9. Documentação (pedido: "todo documentado")

- `README.md` — visão geral + quickstart local
- `docs/ARCHITECTURE.md` — decisões, fluxos, modelo de dados
- `docs/API.md` — API do Hermes agent (endpoints, autenticação, exemplos)
- `docs/DEPLOY.md` — passo a passo Dokku + cron + variáveis
- `docs/DEV.md` — ambiente de dev, testes, comandos
- Este spec.

## 10. Testes

`pytest`/`django.test`:
- Normalização de cada adapter com fixtures (exemplos do `doc_api.md`).
- Detecção automática por máscara.
- Regras: estado final encerra; dedupe; atraso; cota; J&T sem doc.
- API: auth por chave, CRUD, filtros.
- Views web: listagem/detalhe/cadastro.

## Fora de escopo (YAGNI)

- E-mail/notificações push.
- Múltiplos usuários.
- Cache de terceiros (Redis) — mantém simples; escala quando precisar.
- Suporte a transportadoras além das 6 da API.