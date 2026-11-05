# Granite Query website inference integration

A separate trial interface connects the research website to the pinned original Granite checkpoint. Interactive output is distinct from the published research evidence and does not establish improved accuracy. The implementation is disabled by default and requires deliberate server configuration.

## Architecture

The browser uses same-origin Vercel API routes. The gateway validates input, model identity and the serving contract before forwarding to an authenticated Modal backend. Backend admission enforces a bounded quota, expiry and duplicate-request protection. Provider credentials remain on the server.

- `GET /api/model` returns reviewed model metadata and availability.
- `POST /api/generate` accepts `prompt`, `variant`, a UUID `request_id` and optional `max_new_tokens`.
- Responses include model/checkpoint identity, generated text, token counts and truncation state.
- Normalized errors distinguish work that did not start from an uncertain completion. The browser and gateway do not automatically retry generation.
- One deployment advertises one selected variant. It never silently substitutes a correction adapter for the original model.

The visitor interface is in `docs/try/`. It reads metadata before offering a submission, writes a request receipt to tab-local session storage before dispatch and retains uncertain receipts across reloads. Model output is rendered as text. Question text and answers are not stored in that session receipt.

The earlier `docs/demo/` prototype has a different service contract and is excluded from deployment. Research reports, evaluation data, accepted animation code and Design Lab visibility are independent of this integration.

## Deployment source

Use reviewed GitHub source, with the repository root as the Vercel project root and `docs` as the static output directory. No framework, install command or build command is required. Root `api/*.mjs` files are Node functions and shared gateway logic stays in `server/`. The project targets Node 24.

Do not deploy the shared research workspace wholesale. Its unpublished outputs are not website assets. `.vercelignore` excludes research artifacts, environment files and local demo drafts. Publish an explicit file whitelist and preserve unrelated remote files.

A custom domain can remain registered and hosted for DNS at its current registrar. Add it to the intended Vercel project, read that project's exact DNS requirements, and change only the required hosting records after release approval. Preserve unrelated records. Domain assignment alone does not establish working DNS or HTTPS.

## Server configuration

The gateway requires these server-only environment variables:

| Variable | Purpose |
| --- | --- |
| `GRANITE_INFERENCE_ENABLED` | Explicit enable gate; otherwise no upstream request is made. |
| `PUBLIC_SITE_ORIGIN` | Exact allowed HTTPS website origin. |
| `MODAL_INFERENCE_BASE_URL` | Fixed authenticated backend URL. |
| `MODAL_PROXY_TOKEN_ID`, `MODAL_PROXY_TOKEN_SECRET` | HTTP proxy credentials, separate from deployment credentials. |
| `GRANITE_MODEL_REVISION` | Pinned model revision. |
| `GRANITE_CHECKPOINT_ID`, `GRANITE_CHECKPOINT_VARIANT` | Explicit checkpoint and variant identity. |
| `GRANITE_TRIAL_EXPIRES_AT_UTC` | Expiry matching the backend contract. |
| `GRANITE_DURABLE_ADMISSION_CONFIRMED` | Operator confirmation after validating admission controls. |
| `GRANITE_PROXY_AUTH_CONFIRMED` | Operator confirmation after validating backend authentication. |

Origin checks are not visitor authentication or a spending limit. The backend must separately enforce its reviewed admission contract. Verify a credential's actual provider scope before approving it; never assume it is limited to one endpoint or environment. Operator confirmations are gates, not proof by themselves.

Keep live account state, allowances, endpoint URLs, credential identifiers, trial timing, cleanup instructions and verification receipts in the private operator record. They do not belong in public documentation. Never place credential values in browser code or repository files.

## Verification

```text
node --test server/inference-gateway.test.mjs
python -B -m unittest granite_query.cloud.test_demo_serving_v1
```

The gateway and admission suites cover input bounds, disabled configuration, identity and expiry checks, safe error handling, durable admission and replay prevention. These offline tests do not dispatch inference. The browser interface has been checked on desktop and narrow layouts, including keyboard access and fail-closed behavior. A separate private record contains actual end-to-end verification and release readiness; connectivity checks are not accuracy or cost benchmarks.

The experimental backend is in `granite_query/cloud/demo_serving_v1.py` and `modal_demo_api_v1.py`. Execute provider commands from `granite_query` using the module path `cloud.modal_demo_api_v1`. An explicit private artifact/admission manifest must exist; no checkpoint, quota or funding is selected automatically. Preserve the older research and final-checkpoint serving contracts.

Official references: [Vercel Node functions](https://vercel.com/docs/functions/runtimes/node-js), [Vercel project configuration](https://vercel.com/docs/project-configuration/vercel-json), [Modal proxy authentication](https://modal.com/docs/guide/webhook-proxy-auth).

