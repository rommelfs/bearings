# Licensing and source availability

Bearings is licensed under **AGPL-3.0-or-later**, as explicitly selected by the owner on 2026-10-16. Recipients may use GNU AGPL version 3 or any later version. [LICENSE](../LICENSE) contains the full text from the [SPDX license data](https://github.com/spdx/license-list-data/blob/main/text/AGPL-3.0-or-later.txt); `pyproject.toml` declares the exact SPDX expression. GitHub's generic `AGPL-3.0` detection does not replace the project's explicit “or later” grant.

The repository is public at https://github.com/rommelfs/bearings. The application footer links to its source and license; the development image retains LICENSE. Deployers modifying the application must provide the corresponding source to remote users as required by AGPL section 13, including their modifications and applicable build/install material. An unmodified upstream source link is insufficient for a modified deployment.

No copyright ownership or assignment to CIRCL is invented. Contributions must be compatible with the project license and preserve required upstream notices. Operational data and third-party intelligence are not relicensed by this source-code license.

## Initial dependency and integration review

Reviewed on 2026-10-16 using installed distribution metadata/license files and upstream GitHub license records. Dependencies are consumed through the lockfile; upstream application source is not vendored.

| Component | Reviewed license |
| --- | --- |
| Django 5.2.18, httpx 0.28.1, asgiref 3.12.1, httpcore 1.0.9, idna 3.20 | BSD-3-Clause |
| sqlparse 0.6.0 | BSD-3-Clause (installed LICENSE inspected) |
| psycopg / psycopg-binary 3.3.6 | LGPL-3.0-only |
| anyio 4.15.1, h11 0.16.0 | MIT |
| certifi 2026.7.22 | MPL-2.0 |
| typing-extensions 4.16.0 | PSF-2.0 |
| NetBox | Apache-2.0 (upstream API application) |
| MISP, Vulnerability-Lookup, Plum Island | AGPL-3.0 family reported by upstream license records; retain each project's exact terms |

These projects retain their own licenses. Preserve distribution notices and inspect the exact selected release and any bundled native libraries when packaging or redistributing artifacts. Psycopg binary wheels include native components with their own notices; the public source repository does not vendor these wheels. Data/API redistribution permissions, particularly MISP intelligence, remain separate from software licensing. Repeat the review when dependencies, deployed upstream releases or distribution artifacts change.

The optional development stack uses official NetBox (Apache-2.0), Valkey (BSD-3-Clause), Nginx (BSD-2-Clause) and PostgreSQL (PostgreSQL License) images. Those images retain upstream licenses/notices and are not relicensed by Bearings' AGPL grant. No upstream application source is vendored.
