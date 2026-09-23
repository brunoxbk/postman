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
  COTA_MENSAL=900 \
  PACOTE_NOTIFY_EMAIL="voce@example.com" \
  DJANGO_DEFAULT_FROM_EMAIL="postman@example.com"
```

`DATABASE_URL` já é injetada pelo plugin `postgres:link`. Habilite HTTPS e o domínio:

```bash
dokku domains:add postman postman.example.com
dokku letsencrypt:enable postman   # plugin https://github.com/dokku/dokku-letsencrypt
```

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

Edite o crontab do **host** (não dentro do container):

```bash
crontab -e
```

```cron
# America/Sao_Paulo. (Ajuste o fuso do host OU use CRON_TZ)
40 8 * * * dokku run postman python manage.py sync_trackings >/dev/null 2>&1
0  13 * * * dokku run postman python manage.py sync_trackings >/dev/null 2>&1
0  19 * * * dokku run postman python manage.py sync_trackings >/dev/null 2>&1
```

Se o fuso do host não for America/Sao_Paulo, prefixe com `CRON_TZ=America/Sao_Paulo`
(disponível no cronie/Vixie recentes) ou converta os horários para o fuso do host.

Valide manualmente antes de confiar no cron:

```bash
dokku run postman python manage.py sync_trackings
```

## 6. Health check

Para uso por monitors/uptime e pós-deploy:

```bash
curl -H "Authorization: Api-Key $KEY" https://postman.example.com/api/v1/health/
```

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