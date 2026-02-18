# Bear Blog API

Available to upgraded accounts only. All endpoints return JSON.

## Authentication

Pass your blog's API token in every request:

```
Authorization: Bearer <token>
```

Find your token under **Advanced Settings → API access** in the dashboard. You can generate or regenerate it there.

Each token is scoped to a single blog. Requests are authenticated against the blog that owns the token.

---

## Endpoints

### List posts

```
GET /api/v1/posts/
```

Returns all posts for the blog, ordered by `published_date` descending (includes drafts). Returns summary fields only — use `GET /api/v1/posts/<uid>/` to retrieve full post data including `content`.

**Response**

```json
{
  "posts": [
    {
      "uid": "AMuVteLATkHCHMmhGGra",
      "title": "Hello World",
      "slug": "hello-world",
      "publish": true,
      "published_date": "2024-01-15T12:00:00+00:00",
      "tags": ["intro", "meta"],
      "is_page": false
    }
  ]
}
```

---

### Get a post

```
GET /api/v1/posts/<uid>/
```

**Response** — same fields as a single item from the list above.

---

### Create a post

```
POST /api/v1/posts/
Content-Type: application/json
```

**Request body**

Only `title` and `content` are required. All other fields are optional.

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `title` | string | yes | | |
| `content` | string | yes | | Markdown |
| `slug` | string | | auto | Generated from title via `slugify` if omitted |
| `publish` | boolean | | `true` | `false` saves as draft |
| `published_date` | ISO 8601 string | | now | e.g. `"2024-06-01T09:00:00Z"` |
| `tags` | array of strings | | `[]` | |
| `meta_description` | string | | `""` | |
| `meta_image` | string | | `""` | URL |
| `is_page` | boolean | | `false` | Treats post as a static page |
| `make_discoverable` | boolean | | `true` | Include in Bear Blog discovery feed |
| `canonical_url` | string | | `""` | For syndicated content |

**Example**

```bash
curl -X POST https://yourblog.bearblog.dev/api/v1/posts/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My new post",
    "content": "Hello from the API.",
    "publish": true,
    "tags": ["api"]
  }'
```

**Response** — `201 Created`, full post object.

---

### Update a post

```
PUT /api/v1/posts/<uid>/
Content-Type: application/json
```

Full replacement. All writable fields are overwritten — omitted fields revert to their defaults. Send the complete post object.

**Example**

```bash
curl -X PUT https://yourblog.bearblog.dev/api/v1/posts/<uid>/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated title",
    "content": "Updated content.",
    "slug": "updated-title",
    "publish": true,
    "published_date": "2024-01-15T12:00:00Z",
    "tags": [],
    "meta_description": "",
    "meta_image": "",
    "is_page": false,
    "make_discoverable": true,
    "canonical_url": ""
  }'
```

**Response** — `200 OK`, full post object.

---

### Delete a post

```
DELETE /api/v1/posts/<uid>/
```

**Response**

```json
{ "deleted": true }
```

---

## Post object

`uid` is read-only and assigned on creation. All other fields are writable via POST/PUT.

Posts with `is_page: true` are pages rather than blog posts. They do not appear in the post list or RSS feed.

| Field | Type | Read-only |
|---|---|---|
| `uid` | string | yes |
| `title` | string | |
| `slug` | string | |
| `content` | string (Markdown) | |
| `publish` | boolean | |
| `published_date` | ISO 8601 string | |
| `tags` | array of strings | |
| `meta_description` | string | |
| `meta_image` | string (URL) | |
| `is_page` | boolean | |
| `make_discoverable` | boolean | |
| `canonical_url` | string | |

---

## Rate limiting

**10 requests per 10 seconds** per API token. When the limit is exceeded the API returns `429 Too Many Requests` with a `Retry-After` header indicating how many seconds to wait before retrying.

---

## Errors

| Status | Meaning |
|---|---|
| `400` | Invalid JSON in request body |
| `401` | Missing or invalid token |
| `403` | Account is not upgraded |
| `404` | Post not found (or belongs to a different blog) |
| `405` | HTTP method not supported on this endpoint |
| `429` | Rate limit exceeded |

All error responses have the shape:

```json
{ "error": "Human-readable message" }
```
