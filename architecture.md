# Bear Architecture

Bear is a Django-based blogging platform. Users get a subdomain at `*.bearblog.dev` or can point a custom domain.

## Stack

- **Framework:** Django 5.2, Python 3.13
- **Server:** Gunicorn (`conf.wsgi`), 24s timeout, max 10k requests per worker
- **Database:** Heroku Postgres (via `dj-database-url`). SQLite used locally.
- **Cache / Sessions:** RedisCloud (TLS). Falls back to no cache in dev.
- **Static files:** WhiteNoise (GZip compressed)

## Deployment

Bear runs on **Heroku** (`bear-blog` app). The `Procfile` runs migrations on release and starts Gunicorn on web.

Heroku Postgres is backed up locally on a daily schedule.

There is **no staging server**.

## Routing

### bearblog.dev subdomains
Cloudflare handles DNS and SSL for `*.bearblog.dev`. Cloudflare also does the heavy lifting for caching and bot deterrence. Cache is invalidated per-blog using Cloudflare cache tags (keyed on subdomain) whenever a blog or post is saved.

### Custom domains
A **Caddy** server running on a Digital Ocean droplet handles custom domain SSL and reverse proxies to `https://bearblog.dev`. It uses on-demand TLS, verifying domains by querying `https://bearblog.dev/ping/` before issuing a cert.

Caddy config: `Caddyfile` in repo root.

### Main site routing
The `MAIN_SITE_HOSTS` env var (`www.bearblog.dev,bearblog.dev`) gates staff and discover routes. Requests to any other host are treated as blog subdomain/custom domain requests.

## Storage

### Images
User-uploaded images go to a **Digital Ocean Spaces** S3 bucket. The DO CDN serves them.

### Blog backups
Reviewed blog content (posts + blog metadata as CSV) is backed up to a separate DO Spaces bucket (`bear-backup`, region `fra1`) in a background thread whenever a blog is saved.

## Services

| Service | Purpose |
|---------|---------|
| **Cloudflare** | DNS, SSL (`.bearblog.dev`), caching, bot deterrence |
| **Heroku Postgres** | Primary database |
| **RedisCloud** | Cache + session store |
| **Digital Ocean Spaces** | Image CDN + blog content backups |
| **Digital Ocean Droplet** | Caddy reverse proxy for custom domains |
| **LemonSqueezy** | Subscription payments. Webhooks upgrade/downgrade `UserSettings`. |
| **Mailgun** | Transactional email (SMTP via `smtp.eu.mailgun.org`) |
| **Sentry** | Error tracking (production only, low sample rate) |
| **JudoScale** | Heroku autoscaling — passive unless under load |
| **Akismet** | Spam detection (secondary to dodginess score) |
| **GeoIP2** | Geolocation for analytics |

## Key Models

- **`UserSettings`** — per-user upgrade status, LemonSqueezy order info
- **`Blog`** — subdomain, custom domain, styles, discovery settings, dodginess score
- **`Post`** — content, slug, tags, upvotes, HN-style score for discover feed
- **`Hit`** — analytics hits (hash_id scrubbed after 24h for privacy)
- **`Subscriber`** — email subscribers per blog
- **`Stylesheet`** — named CSS themes
- **`Media`** — uploaded image URLs per blog
- **`PersistentStore`** — singleton for platform-wide settings (review terms, blacklist)

## Discovery Feed & Moderation

Unreviewed blogs get a `dodginess_score` computed from highlight/blacklist terms in `PersistentStore`. Upgraded users are auto-reviewed. Staff can approve, block, ignore, or flag blogs via `/staff/`.

Post scores use an HN-style algorithm (log of upvotes + time decay, capped at 30 upvotes to prevent permanent stickiness).

## Middleware (in order)

1. `RateLimitMiddleware` — 10 req/10s per IP, bans on `.php`/`.env` probes and SQL injection patterns
2. `ConditionalXFrameOptionsMiddleware` — `X-Frame-Options: DENY` on main domains only
3. GZip, Security, WhiteNoise, Sessions, DebugToolbar, Common
4. `AllowAnyDomainCsrfMiddleware` — custom CSRF handling to support custom domains

