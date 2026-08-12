# Desktop App API

This API is for the desktop software only. It is read-only for data pulls, except for device registration and revocation.

## Security model

- Registration requires the bootstrap header `X-Desktop-Bootstrap` or an authenticated `super_admin` session.
- Each desktop installation gets its own long-lived access token.
- The server stores only a hash of the access token.
- Active desktop installations are capped at 5.
- All data endpoints require `Authorization: Bearer <access_token>` or `X-Desktop-Api-Key`.
- Direct file downloads are limited to safe media paths only.

## Environment variables

- `DESKTOP_APP_ENABLED=1`
- `DESKTOP_APP_BOOTSTRAP_TOKEN=...`
- `DESKTOP_APP_MAX_CONNECTIONS=5`
- `DESKTOP_APP_TOKEN_MAX_AGE_SECONDS=2592000`

## Endpoints

### Register a device

`POST /api/desktop/register/`

Headers:

- `X-Desktop-Bootstrap: <bootstrap token>`

Body:

```json
{
  "device_name": "Main Office Desktop",
  "installation_id": "office-desktop-01"
}
```

Response returns the desktop access token once.

### Check status

`GET /api/desktop/status/`

### Pull manifest

`GET /api/desktop/clients/`

Optional query params:

- `client_id=<id>`
- `table_id=<id>`

Returns a JSON object containing the full data manifest:
- `clients`: List of all returned clients.
- `groups`: List of table groups.
- `tables`: List of all ID card tables.
- `cards`: List of cards including their status (e.g., approved/downloaded counts context) and field data. The cards are ordered by descending ID to perfectly match the ordering of XLSX exports.
- `media`: List of media file metadata.

### Download full export

`GET /api/desktop/export/`

Optional query params:

- `client_id=<id>`
- `table_id=<id>`

Returns a ZIP archive containing:

- `manifest.json`
- `clients.json`
- `groups.json`
- `tables.json`
- `cards.json`
- `media.json`
- `original_images/...`

### Download images zip only

`GET /api/desktop/export-images/`

Optional query params:

- `client_id=<id>` (Filter by client ID)
- `group_id=<id>` (Filter by group ID)
- `table_id=<id>` (Filter by table/list ID)
- `status=<approved|download|both>` (Filter by card status, defaults to `both`)

Returns a ZIP archive containing only the image files inside `original_images/...` without any JSON files (such as `manifest.json`, `cards.json`, etc.).

### Download a single file

`GET /api/desktop/download/<relative_path>/`

The path must stay inside approved media folders such as `adarshimg/`, `card_media/`, `id_photos/`, `clients_imgs/`, `staff_imgs/`, or `temp/`.

## Request example

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.example/api/desktop/clients/
```

## Desktop integration notes

- Cache the returned access token securely on the desktop machine.
- Send the token on every request.
- Use `/export/` for bulk sync and `/download/<path>/` for file-by-file pulls.
- If the API returns `Desktop connection limit reached`, revoke an unused device before registering another one.
