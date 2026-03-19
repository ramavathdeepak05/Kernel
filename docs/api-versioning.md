# ALIS API Versioning Policy

## Overview

ALIS uses URL-based API versioning (`/api/v1/`, `/api/v2/`). This document defines
the versioning strategy, deprecation process, and migration guidance for integrators.

## Version Lifecycle

| Status | Description |
|---|---|
| **Current** | Fully supported, receives all new features |
| **Deprecated** | Supported but no new features; sunset date announced |
| **Sunset** | Removed; requests return `410 Gone` |

## Current Versions

| Version | Status | Introduced | Sunset Date |
|---|---|---|---|
| `v1` | Current | Phase 0 (Oct 2025) | TBD — announced 12 months prior |
| `v2` | Planned | Phase 4 (Mar 2026) | — |

## Deprecation Process

1. **Announce** — deprecation published in changelog + `Deprecation` response header on affected endpoints
2. **Sunset header** — `Sunset: <RFC 7231 date>` added to all deprecated endpoint responses
3. **12-month runway** — minimum 12 months between deprecation announcement and sunset
4. **Final notice** — 30-day reminder via ops email before sunset date
5. **Removal** — endpoint returns `410 Gone` with migration instructions in body

### Example Deprecation Headers
```
Deprecation: true
Sunset: Thu, 01 Jan 2027 00:00:00 GMT
Link: </api/v2/admissions>; rel="successor-version"
```

## Breaking vs Non-Breaking Changes

### Non-breaking (allowed in existing version)
- Adding new optional request fields
- Adding new response fields
- Adding new endpoints
- Adding new enum values to non-exhaustive enums

### Breaking (requires new version)
- Removing or renaming fields
- Changing field types or formats
- Removing endpoints
- Changing authentication requirements
- Changing error response shape

## v2 Design Principles

v2 endpoints follow the same auth, RBAC, and tenant isolation model as v1. Key improvements:

- Cursor-based pagination (`cursor` + `limit`) instead of `page` + `per_page`
- Consistent envelope: `{ data: T, meta: PaginationMeta, links: CursorLinks }`
- ISO 8601 durations for time fields (no more integer seconds)
- `problem+json` error format (RFC 7807)

## Client Migration Checklist

- [ ] Pin to a specific version in your base URL (`/api/v1/` not `/api/`)
- [ ] Subscribe to `Sunset` header warnings (log or alert when present)
- [ ] Test against v2 sandbox before v1 sunset
- [ ] Update `Accept` header to `application/json; version=2` where required

## Internal: Adding a New v2 Endpoint

Use the `VersionedRouter` helper in `server/core/api_versioning.py`:

```python
from server.core.api_versioning import VersionedRouter

v2_router = VersionedRouter(version=2, prefix="/api/v2")

@v2_router.get("/admissions")
async def list_applications_v2(...):
    ...
```

The `VersionedRouter` automatically:
- Adds `X-ALIS-API-Version: 2` response header
- Attaches `Deprecation` + `Sunset` headers to v1 counterparts when configured
- Registers the route in OpenAPI with the correct tags

## References

- RFC 7807 — Problem Details for HTTP APIs
- RFC 8594 — The Sunset HTTP Header Field
- [ALIS Architecture](../ALIS/server/core/api_versioning.py)
