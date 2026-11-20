# pyapp_template

Copier generator for Python 3.14 async services, managed with uv. Choose FastAPI,
FastMCP (HTTP or stdio), optional SQLAlchemy asyncio/Alembic, typed settings and
an outbound HTTP client. Generated projects contain no CI, Docker, authentication,
Redis, business models, or deployment machinery.

## Generate

Install Python 3.14 and uv, then run:

```sh
uvx --from 'copier>=9.11,<10' copier copy gh:D506n/pyapp_template my-service
```

Select the generated project's license explicitly: `MIT` or `none`. The generator's
MIT license does not automatically license your generated application. `none` omits
the application license file and metadata; choose a license before distributing it.

Before this branch is merged, validate a local candidate (HEAD uses its working tree):

```sh
uvx --from 'copier>=9.11,<10' copier copy --vcs-ref=HEAD ./path/to/candidate ./my-service
```

For reproducible noninteractive generation, supply the license and answers explicitly:

```sh
uvx --from 'copier>=9.11,<10' copier copy --defaults \
  -d project_name=my-service -d package_name=my_service \
  -d project_license=MIT -d use_http_api=true -d use_mcp=false \
  gh:D506n/pyapp_template my-service
cd my-service
uv lock
uv sync --locked
uv run python -m my_service
```

Generation writes files only: no install, network bootstrap, Git initialization,
lockfile generation, secrets or migrations. Remote source retrieval by Copier itself
requires network. Review generated files before running the separate bootstrap.
`uv lock` resolves a real `uv.lock`; `uv sync --locked` installs that resolution.

## Choices and constraints

| Question | Values / default |
| --- | --- |
| project_name | lowercase distribution name; `my-service` |
| package_name | safe lowercase Python package; derived from project name |
| description, author_name | free text; escaped in metadata |
| project_license | explicit `MIT` or `none`; no implicit default |
| use_http_api / http_framework | true / FastAPI |
| use_mcp | false |
| mcp_transport | HTTP or stdio for MCP-only; HTTP when combined |
| database | none (default), postgresql, sqlite, mysql |
| use_alembic | false; SQL only |
| use_settings | true; pydantic-settings, no implicit .env |
| use_http_client | false; httpx AsyncClient with timeout |

At least one interface is required. Invalid names, reserved module names and
incompatible choices are rejected. Distribution names and import package names are
reserved against the supported runtime, development and build dependency union, even
when an option is disabled. These explicit lists must be updated when dependencies
change; they do not predict names of unknown future dependencies. Combined interfaces share one ASGI service;
MCP mounts at `/mcp`, allowing the normal redirect to `/mcp/`. FastAPI preserves incoming `X-Trace-ID` in a request-local ContextVar; absent means
`None`, no ID is generated and no response header is added.
Bind defaults to
loopback. MCP stdio writes its protocol to stdout and logs to stderr.

SQL selects only its async driver: asyncpg, aiosqlite or asyncmy. Supply
`DATABASE_URL` explicitly at runtime; URLs must match the chosen driver. Import and
startup never connect to the database or create tables. Alembic commands are manual,
use async connections and empty initial metadata; review each generated revision
before applying it to an explicitly selected environment.

## Generator development

```sh
uv lock
uv sync --locked
just precommit-check-agent
```

See AGENTS.md, AGENTS.project.md and CODESTYLE.md. Tests and security checks apply
to the generator and representative generated applications. The application runtime
does not depend on Copier. HTTPX in the development group supports transport checks
and does not enable the optional runtime client.

MIT © D506n. Generated-project licensing is a separate explicit choice.

The original template MIT notice is retained in `THIRD_PARTY_NOTICES.md` in generated
projects, including when the project license is `none`. This does not license newly
added project code automatically.
