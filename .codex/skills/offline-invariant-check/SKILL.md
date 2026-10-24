---
name: offline-invariant-check
description: Check local-first guarantees when adding or changing network, AI, synchronization, or optional-provider code.
---

# Offline invariant verification

KiPart Manager's core must remain functional with no network, server, or AI provider.

Use this skill when work introduces or changes:

- HTTP access;
- remote resolvers;
- AI providers;
- synchronization;
- update checking;
- optional online metadata;
- application startup behavior involving external services.

Check that:

1. Core/domain modules do not import online provider implementations.
2. Application startup does not require network connectivity.
3. Optional providers can be absent.
4. Network failures degrade to explicit optional-feature failures rather than breaking the application.
5. Local catalogue, inventory, asset management, KiCad indexing, validation, publication, and portable import/export remain architecturally independent of remote services.
6. Tests can exercise the relevant local path with network access blocked or mocked unavailable.

Do not create fake online fallbacks that silently alter local data.
