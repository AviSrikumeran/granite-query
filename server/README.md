# Granite Query website API foundation

The public GitHub Pages design is unchanged. This separate Vercel/Modal integration is disabled by default. One private original-Granite request succeeded on A10G. A bounded private Modal trial is deployed, and the protected Vercel preview renders the new `/try/` interface with inference disabled. Authenticated website generation, production release and custom-domain DNS are not yet verified. The source remains in a draft PR.

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

Use the reviewed GitHub branch, with **Project Root at the repository root**, `outputDirectory: docs`, no framework and no install/build command. Root `api/*.mjs` files are Vercel Node functions; shared logic stays in `server/`. The project targets Node 24. The Vercel configuration gives functions 240 seconds; the gateway stops waiting after 170 seconds by default, with a 200-second maximum. These bounds accommodate the prepared backend's 60-second startup and 90-second execution envelope plus web preflight; they are not measured serving latency. A timeout means completion is unknown, not that no GPU work happened.

Do not deploy this shared local working directory wholesale. It contains concurrent unpublished research outputs and demo drafts. `.vercelignore` excludes private research and the unverified demo, but GitHub source and a focused release whitelist remain the authoritative deployment boundary. Never upload model weights, private run records or environment files as website assets.

The Vercel project is accessible. Its protected preview renders the unchanged homepage, Results, library and journal, plus the disabled trial form. The unconfigured `/api/model` returned the expected `not_configured` error. A temporary preview share link was revoked. `granitequery.live` is assigned to this project, but the inspected Squarespace hosting records remain unchanged. Vercel supplied the exact apex A-record target **76.76.21.21**. Verify production release before changing hosting DNS; preserve unrelated email records. Domain assignment is not proof that DNS or public serving is connected. Do not buy or transfer the domain again.

## Gateway contract

- `GET /api/model` returns versioned public model metadata only when the configured private backend matches its pinned checkpoint, revision, expiry and request limits. Unconfigured deployments return HTTP 503 with `error.code: not_configured` and make no upstream call.
- `POST /api/generate` takes a JSON object containing `prompt`, `variant`, UUID `request_id` and optional integer `max_new_tokens`. Limits are 16 KiB, 1–2400 trimmed prompt characters and 1–512 output tokens. The backend additionally enforces token/context bounds before GPU dispatch.
- One deployment advertises one explicitly selected variant. The gateway rejects unsupported variants rather than silently substituting the original model or a correction adapter.
- Success includes actual output, checkpoint and request identity, token counts, elapsed time and truncation. Errors use `error.code`, `message`, `retryable: false` and `completion: not_started | unknown`. No raw provider exception or private path is forwarded.
- The interface must generate one UUID per deliberate submission and retain it on ambiguous failure. It must not automatically resubmit. Choosing to try another prompt is a new request, not recovery of the earlier result.

The earlier local `docs/demo/demo.js` prototype uses a different service identity and variant contract. It remains excluded from deployment. The separate `docs/try/` interface checks metadata once, supports the advertised original checkpoint, retains a UUID receipt before submission and never automatically retries a generation. An uncertain completion stays locked across a tab reload until explicitly acknowledged. Existing public navigation is unchanged.

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

The current foundation passes **40 offline checks: 18 Node gateway tests and 22 Python contract/admission tests**, plus an offline cross-language metadata check. These checks do not dispatch inference.

The owner selected original Granite first and authorized an initial **$30 serving ceiling**. This is a spending authorization, not a provider balance, observed charge or recurring budget. Private receipts record three distinct dispatches on November 5; none was an automatic retry:

1. The first L4 worker passed bundle hashes and tokenization, then failed its original 35-second preparation guard before model loading or generation. Its permit remains consumed.
2. The second L4 dispatch never entered the worker; provider evidence confirmed unavailable capacity. It produced no answer and remains separate from the first failure.
3. The third dispatch succeeded on **NVIDIA A10G**, serving the pinned original checkpoint. It returned the expected numeric answer **37**, generated **62 tokens**, and reported **24.012 seconds inside the worker**, including **2.393 seconds loading the model** and **3.104 seconds generating**. The saved diagnostics also report 10.852 seconds hashing, 7.053 seconds runtime setup and 0.355 seconds tokenization.

An earlier UTF-8 preparation attempt ended with empty input and dispatched **zero GPU requests**; it is not a fourth model execution. Unauthenticated HTTP requests during the private tests were rejected with 401. The ephemeral verification app contexts were closed, and the earlier stopped-app observations remain in the private receipts.

The A10G result verifies one private runtime request, not benchmark accuracy, end-to-end website latency, a warm-request measurement or a clean storage-cold baseline. The private model files had already been read for hash verification; storage caching may have affected timing. Worker elapsed time excludes image build, provider queue/container startup and the Vercel/browser path. No request cost is inferred from this timing, and no actual serving-charge total is claimed.

The code includes the explicitly hashed `chat_template.jinja`, omits the SDK-incompatible CPU-webhook retry option, loads weights directly onto CUDA, and records phase/memory diagnostics. The 60-second preparation guard succeeded in the private A10G check within the 80-second work budget and 90-second function timeout. This does not establish L4 feasibility or the longer gateway's HTTP behavior. Live duplicate-claim, dispatch and worker-entry checks each rejected the already-consumed successful request with 409; its used-permit count stayed at one and no new GPU dispatch occurred.

A separate private A10G deployment was prepared with a fresh, explicit 20-request namespace and four-hour expiry, then stopped while credential-scope approval is pending. Its immutable manifest and permits are preserved. It uses proxy authentication and no warm GPU pool. On Modal Starter, proxy tokens are workspace-wide unless RBAC is enabled; they cannot be assumed to be limited to one environment. An unused token from a failed environment-association step was deleted before configuring Vercel. A workspace-wide HTTP credential requires the owner's explicit scope approval. Production release is a separate approval from preview preparation. No server secret has yet been configured, and no authenticated HTTP generation is claimed.

The separate experimental backend lives in `granite_query/cloud/demo_serving_v1.py` and `modal_demo_api_v1.py`. Run its offline checks with `python -B -m unittest granite_query.cloud.test_demo_serving_v1` from the repository root. Future Modal execution must use `granite_query` as the working directory and `cloud.modal_demo_api_v1` as the module path. Its private base bundle and explicit variant/allowance manifest must exist before deployment; nothing is auto-selected or auto-funded.

Before live serving: verify the protected Vercel deployment routes; finish the bounded private Modal deployment with its explicit original-checkpoint manifest; initialize its deliberate quota namespace without resetting prior permits; confirm unauthenticated denial on that deployment; connect server secrets; and perform an explicitly authorized HTTP request through the gateway and `/try/` form. Keep cold/warm measurements and any later cost reconciliation distinct from the one private result. DNS and public inference are not considered connected until verified.

Official references checked November 5, 2026: [Vercel Node functions](https://vercel.com/docs/functions/runtimes/node-js), [Vercel configuration](https://vercel.com/docs/project-configuration/vercel-json), [Modal proxy authentication](https://modal.com/docs/guide/webhook-proxy-auth), [Squarespace hosting DNS](https://support.squarespace.com/hc/en-us/articles/31119879125645-DNS-records-for-web-hosting).

