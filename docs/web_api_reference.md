# Public Client List Sharing API Reference

This document describes the API endpoint designed to share the client list and aggregate record counts with the landing website.

> 📖 **Full Guide**: For detailed client code examples in Next.js, Node.js, Python, PHP, caching strategies, and architecture diagrams, see [WEB_APP_INTEGRATION.md](WEB_APP_INTEGRATION.md).

---

## 🔐 Authentication

Authentication is performed using a server-to-server API Key.

* **Header Name**: `X-API-KEY`
* **Query Parameter Alternative**: `api_key` (e.g. `?api_key=YOUR_SECRET_KEY`)

The secret API key is configured on the backend using the environment variable `WEB_APP_API_KEY`. If not defined in the environment, it defaults to a secure fallback key.

---

## 📡 Endpoint Details

### Get Clients List

Expose all client profiles including their name, email, and the total count of cards/records across all of their lists combined.

* **URL**: `/api/web/clients/`
* **Method**: `GET`
* **Format**: JSON

#### Headers
| Header | Value | Description |
| :--- | :--- | :--- |
| `X-API-KEY` | `YOUR_SECRET_API_KEY` | **Required.** The secret authentication key configured on the portal server. |
| `Accept` | `application/json` | Optional. |

---

## 📝 Request & Response Examples

### Example Request (curl using headers)
```bash
curl -X GET \
  -H "X-API-KEY: adarsh_secure_fallback_key_2026_web_app" \
  http://localhost:8000/api/web/clients/
```

### Example Request (using query parameters)
```bash
curl -X GET http://localhost:8000/api/web/clients/?api_key=adarsh_secure_fallback_key_2026_web_app
```

### Success Response (200 OK)
```json
{
  "success": true,
  "clients": [
    {
      "name": "Alpha School",
      "email": "alpha@example.com",
      "total_records": 250
    },
    {
      "name": "Beta Convent School",
      "email": "beta@example.com",
      "total_records": 12
    }
  ]
}
```

### Unauthorized Response (401 Unauthorized)
Returned if the `X-API-KEY` header or `api_key` query param is missing or incorrect.
```json
{
  "success": false,
  "message": "Unauthorized. A valid X-API-KEY is required."
}
```
