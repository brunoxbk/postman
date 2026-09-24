# Deploy no Dokku

Pré-requisitos: servidor com Dokku instalado e o domínio apontando para o host.

> O build usa a detecção automática do buildpack de Python (via `runtime.txt` +
> `requirements.txt` + `Procfile`). Nada de Dockerfile é necessário.

## 1. Criar o app e o banco

```bash
dokku apps:create postman
dokku postgres:create postman-db
dokku postgres:link postman-db postman
```

> O `sync_trackings` roda **paralelo** (threads, `SYNC_WORKERS`, default 4) e por isso
> **exige Postgres** — é o banco de prod, então nenhuma ação adicional é necessária.
> (O fallback sequencial existe só para SQLite/dev e testes.)

## 2. Configurar variáveis de ambiente

```bash
dokku config:set postman \
  DJANGO_SETTINGS_MODULE=config.settings.prod \
  DJANGO_DEBUG=0 \
  DJANGO_SECRET_KEY="gerar-chave-aleatoria-64-bytes" \
  DJANGO_ALLOWED_HOSTS=postman.example.com \
  PACOTE_VICIO_API_KEY="sua-chave-rapidapi" \
  PACOTE_VICIO_BASE_URL=https://api.pacotevicio.dev \
  PACOTE_VICIO_TIMEOUT=35 \
  COTA_MENSAL=1000 \
  SYNC_WORKERS=4 \
  PACOTE_NOTIFY_EMAIL="voce@example.com" \
  DJANGO_DEFAULT_FROM_EMAIL="postman@example.com" \
  PUBLIC_BASE_URL=https://postman.example.com
```

`DATABASE_URL` já é injetada pelo plugin `postgres:link`. Habilite HTTPS e o domínio:

```bash
dokku domains:add postman postman.example.com
dokku letsencrypt:enable postman   # plugin https://github.com/dokku/dokku-letsencrypt
```

> O `Procfile` sobe o Gunicorn com **2 workers × 2 threads** por padrão. Altere com
> `dokku config:set postman WEB_CONCURRENCY=4` (1 worker já basta para volumes baixos).

## 3. Fazer o push

Da sua máquina (o repositório tem origin apontando para o Dokku):

```bash
git remote add dokku dokku@SEU_HOST:postman
git push dokku main
```

## 4. Primeiras migrações e superusuário (uma vez)

```bash
dokku run postman python manage.py migrate
dokku run postman python manage.py createsuperuser
dokku run postman python manage.py collectstatic --noinput
```

> Se o buildpack rodar `collectstatic` automaticamente e falhar por credenciais,
> desative com `dokku config:set postman DISABLE_COLLECTSTATIC=1` e cole os comandos
> acima no `release` do `Procfile`:
> `release: python manage.py migrate && python manage.py collectstatic --noinput`

## 5. Cron (3×/dia)

O cron roda no crontab do **host** (não dentro do container). Ao contrário da RAM limitada
do container, o host tem o cron do sistema (Vixie-cron do Ubuntu **não** suporta `CRON_TZ`,
então use horários já convertidos para o fuso do host — aqui, **UTC**):

```bash
# root@host
sudo crontab -e
```

```cron
# 08:40/13:00/19:00 America/Sao_Paulo = 11:40/16:00/22:00 UTC (host em Etc/UTC)
40 11 * * * /usr/bin/dokku run postman python manage.py sync_trackings --quiet >> /var/log/sync.log 2>&1
0 16 * * * /usr/bin/dokku run postman python manage.py sync_trackings --quiet >> /var/log/sync.log 2>&1
0 22 * * * /usr/bin/dokku run postman python manage.py sync_trackings --quiet >> /var/log/sync.log 2>&1
```

> Use o **caminho completo do `dokku`** (descubra com `command -v dokku`) e ponha `2>&1`
> no log para diagnosticar falhas. O `sync_trackings` sai com **código ≠ 0** quando alguma
> encomenda falhou ou a cota foi atingida.

O comando roda **apenas encomendas desatualizadas** (`pending_packages()`): com a janela
"no dia", a primeira execução do dia (08:40) sincroniza tudo; as de 13:00 e 19:00 só
pegam o que ainda não foi sincronizado hoje (poupa cota).

Valide manualmente antes de confiar no cron:

```bash
dokku run postman python manage.py sync_trackings
```

## 6. Health check

Para uso por monitors/uptime e pós-deploy:

```bash
curl https://postman.example.com/api/v1/health/
```

> **Health é público** (sem `Api-Key`). Os demais endpoints exigem o header
> `Authorization: Api-Key $KEY`. O schema OpenAPI também é público em
> `https://postman.example.com/api/v1/schema/`.

## 7. Atualizações

A cada push novo, o buildpack executa o `release` (migrate + collectstatic). O cron
continua funcionando sem intervenção. Logs:

```bash
dokku logs postman -t
```

## Troubleshooting

- **`ALLOWED_HOSTS`**: inclua o domínio público; no dev usamos `["*"]`.
- **Static não carrega**: certifique-se de que `whitenoise` está no middleware (já está)
  e que o `collectstatic` rodou.
- **Cota estourando**: monitore `/admin/` (SyncLog) e ajuste `COTA_MENSAL`.
- **E-mails**: se `PACOTE_NOTIFY_EMAIL` estiver preenchido, o cron envia 1 e-mail na
  entrega e 1 na 1ª detecção de atraso. Configure `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/
  `EMAIL_HOST_PASSWORD`/`EMAIL_USE_TLS` no Dokku conforme seu SMTP (defaults do Django).