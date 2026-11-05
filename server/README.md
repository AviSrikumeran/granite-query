# Granite Query website API foundation

The public GitHub Pages design is unchanged. This is a separate Vercel/Modal integration, disabled by default. No successful public generation, GPU serving deployment, latency measurement or serving-cost benchmark has been established.

## Intended path

```text
granitequery.live (domain registered by the owner at Squarespace)
  → Vercel static website (docs/) and same-origin /api routes
  → authenticated Modal Web Function
  → durable request admission and one pinned experimental checkpoint
  → real model output, identity, token counts and truncation state
```

Visitors do not receive provider credentials or need a Modal account. The browser-facing API is still discoverable; origin checks are not user authentication or a spending control. A durable backend quota, expiry and explicit launch allowance are required before enabling inference. No automatic paid retries or indefinite warm GPU pool are intended.

## Deployment source

Use the reviewed GitHub branch, with **Project Root at the repository root**, `outputDirectory: docs`, no framework and no install/build command. Root `api/*.mjs` files are Vercel Node functions; shared logic stays in `server/`. The project targets Node 24. The Vercel configuration gives functions 120 seconds; the gateway stops waiting after 85 seconds by default. A cold backend may exceed that wait, so a timeout means completion is unknown, not that no GPU work happened.

Do not deploy this shared local working directory wholesale. It contains concurrent unpublished research outputs and demo drafts. `.vercelignore` excludes private research and the unverified demo, but GitHub source and a focused release whitelist remain the authoritative deployment boundary. Never upload model weights, private run records or environment files as website assets.

Squarespace can remain the registrar and DNS provider. Add `granitequery.live` to the verified Vercel project, read Vercel's exact DNS/verification requirements, and apply only those hosting records in Squarespace. Do not guess an A/CNAME target or replace unrelated email records. Do not buy or transfer the domain again.

## Gateway contract

- `GET /api/model` returns versioned public model metadata only when the configured private backend matches its pinned checkpoint, revision, expiry and request limits. Unconfigured deployments return HTTP 503 with `error.code: not_configured` and make no upstream call.
- `POST /api/generate` takes a JSON object containing `prompt`, `variant`, UUID `request_id` and optional integer `max_new_tokens`. Limits are 16 KiB, 1–2400 trimmed prompt characters and 1–512 output tokens. The backend additionally enforces token/context bounds before GPU dispatch.
- One deployment advertises one explicitly selected variant. The gateway rejects unsupported variants rather than silently substituting the original model or a correction adapter.
- Success includes actual output, checkpoint and request identity, token counts, elapsed time and truncation. Errors use `error.code`, `message`, `retryable: false` and `completion: not_started | unknown`. No raw provider exception or private path is forwarded.
- The interface must generate one UUID per deliberate submission and retain it on ambiguous failure. It must not automatically resubmit. Choosing to try another prompt is a new request, not recovery of the earlier result.

The earlier local `docs/demo/demo.js` prototype uses a different service identity and variant contract. It remains excluded from deployment. A visitor-facing form still needs to be integrated and verified against this contract after the read-only design review.

## Private configuration

Set these in Vercel server environment variables, never in browser code, a public source file or chat:

| Name | Meaning |
| --- | --- |
| `GRANITE_INFERENCE_ENABLED` | Must be exactly `true` to allow any upstream call; otherwise inference is disabled. |
| `PUBLIC_SITE_ORIGIN` | Exact HTTPS origin, for example `https://granitequery.live`. Preview deployments stay disabled until deliberately configured. |
| `MODAL_INFERENCE_BASE_URL` | Fixed HTTPS base URL for the authenticated app; no username, query or fragment. |
| `MODAL_PROXY_TOKEN_ID`, `MODAL_PROXY_TOKEN_SECRET` | Modal Web Function proxy token pair. These are separate from workspace deployment credentials. |
| `GRANITE_MODEL_REVISION` | Pinned Granite revision `4e9c275e232f10211ec88644d106a1f6a1b60e06`. |
| `GRANITE_CHECKPOINT_ID`, `GRANITE_CHECKPOINT_VARIANT` | Identity of the explicitly approved checkpoint and variant. |
| `GRANITE_TRIAL_EXPIRES_AT_UTC` | Exact UTC expiry matching the backend manifest. |
| `GRANITE_DURABLE_ADMISSION_CONFIRMED` | Operator confirmation after verifying backend quota and duplicate-request behavior. Not proof by itself. |
| `GRANITE_PROXY_AUTH_CONFIRMED` | Operator confirmation after unauthenticated backend requests are verified denied. Not proof by itself. |

The backend must enable `requires_proxy_auth=True`; adding credentials to a Vercel fetch does not protect an otherwise public Modal app. Keep the old final-checkpoint selection and serving contracts unchanged. Any experimental correction checkpoint must have a separate, honest selection/serving contract, frozen artifacts and development-only result labels. It is not an improved or final-test-qualified model.

## Checks and launch sequence

```text
node --test server/inference-gateway.test.mjs
npm run test:site
```

Offline tests use explicit mock responses, not live generation. They check disabled configuration, input bounds, origin, private headers, identity validation, response bounds, safe failures, expiry and no retries.

The current foundation passes 17 Node gateway tests and 19 Python contract/admission tests, plus an offline cross-language metadata check. The Modal declaration was checked by parsing its source; it has not been imported, built or launched as part of these tests.

The separate experimental backend lives in `granite_query/cloud/demo_serving_v1.py` and `modal_demo_api_v1.py`. Run its offline checks with `python -B -m unittest granite_query.cloud.test_demo_serving_v1` from the repository root. Future Modal execution must use `granite_query` as the working directory and `cloud.modal_demo_api_v1` as the module path. Its private base bundle and explicit variant/allowance manifest must exist before deployment; nothing is auto-selected or auto-funded.

Before live serving: verify Vercel workspace access and deployment routes; resolve the experimental checkpoint selection and fresh serving allowance; verify private artifact hashes and actual runtime reload; initialize a new durable quota without resetting old permits; test unauthenticated denial; connect server secrets; perform one explicitly authorized end-to-end generation; measure cold/warm behavior and resource usage; then integrate the visitor form. DNS and public inference are not considered connected until verified.

Official references checked November 5, 2026: [Vercel Node functions](https://vercel.com/docs/functions/runtimes/node-js), [Vercel configuration](https://vercel.com/docs/project-configuration/vercel-json), [Modal proxy authentication](https://modal.com/docs/guide/webhook-proxy-auth), [Squarespace hosting DNS](https://support.squarespace.com/hc/en-us/articles/31119879125645-DNS-records-for-web-hosting).
