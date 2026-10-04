# Hosting and secret management

## Recommended deployment shape

- Deploy `frontend/` to Vercel. Configure `API_BACKEND_URL` as a server-only environment variable containing the HTTPS URL of your FastAPI service. The Next.js rewrite proxies `/api/*` so the browser uses same-origin session cookies. The frontend deployment does not need provider API keys.
- Deploy the FastAPI service to a Python-capable host with HTTPS and persistent PostgreSQL. Configure `PROVIDER_PREFERENCES_DATABASE_URL` on that API service so source enablement, manual routing, and Marketstack's monthly quota counter survive restarts and serverless instances. Vercel deployments fail closed if this database is missing because local files cannot enforce a global request cap across function instances.
- Set `API_CORS_ORIGINS` on the API service to the exact production Vercel origin(s), separated by commas. Set `AUTH_COOKIE_SECURE=true` and use HTTPS for both services.
- GitHub Pages is static hosting and cannot run this FastAPI backend or keep backend secrets. GitHub may hold source code, but never commit `.env`, `.env.local`, private keys, passwords, session secrets, or database URLs.

## Provision the only account

The accepted username is fixed to `AtharvaKh`; there is no public account creation after the initial bootstrap. For hosted instances, create the password verifier locally with:

```powershell
python -m api.auth
```

The command prompts for a password without echoing it and prints the salted PBKDF2 verifier fields. Put those values in the **FastAPI host's private environment** as `AUTH_PASSWORD_HASH` and `AUTH_PASSWORD_SALT`; also set `AUTH_PASSWORD_ITERATIONS` to the printed value. Generate a separate long random `AUTH_SESSION_SECRET` (at least 32 characters) and store it as another private environment value. These settings disable public setup. Do not put any of them in a `NEXT_PUBLIC_*` variable or frontend source.

Passwords are not decryptable: the application stores a salted, deliberately slow PBKDF2-HMAC-SHA256 hash and verifies a login by deriving and comparing a candidate hash. API keys need to be available to the API server to call providers; store them as private runtime environment secrets on the FastAPI host. They are not exposed through API responses or the browser UI. This protects secrets from webpage visitors but cannot protect them from administrators of the hosting account or a compromised backend.

## API credentials and source controls

Set `MARKETSTACK_API_KEY`, `ALPHAVANTAGE_API_KEY`, and other provider keys only in the FastAPI deployment's private environment settings. Do not pass provider keys to Vercel's browser bundle. The Vercel frontend only needs `API_BACKEND_URL`; the backend's provider credentials remain at the backend host. Rotate a credential at its provider and update the corresponding backend secret if it is exposed.

To avoid re-entering keys on future deploys, configure them once as persistent host environment variables; do not upload `.env` into the repository. Vercel environment values are encrypted at rest, while project members with access may still view regular variables. For supported Production and Preview variables, mark credentials **Sensitive** so their values cannot be read back in the dashboard or CLI. The application can use them at runtime without returning them to the frontend. Keep hosting access restricted to you and enable MFA.

For Vercel, set these once in the FastAPI service's private runtime settings: provider credentials from the existing local `.env`, `AUTH_PASSWORD_HASH`, `AUTH_PASSWORD_SALT`, `AUTH_PASSWORD_ITERATIONS`, `AUTH_SESSION_SECRET`, `AUTH_COOKIE_SECURE=true`, `PROVIDER_PREFERENCES_DATABASE_URL`, and `API_CORS_ORIGINS` with the exact Vercel site origin. On the frontend Vercel project, set only `API_BACKEND_URL` to the HTTPS API origin. Deploy a new version after changing environment values. Never create `NEXT_PUBLIC_*` provider credentials.

The administrator-only Data Sources panel stores provider enable/disable choices, automatic failover, and the preferred equity-history provider. For equity history, choose automatic, Marketstack first, or Alpha Vantage first. Automatic failover tries another enabled/configured source when the preferred source is out of quota, errors, or returns no usable dated observations. It cannot make two vendors' coverage or free-plan entitlements equivalent. Alpha Vantage's free daily endpoint may return only its compact recent history; indices and unsupported symbols may remain unavailable. Credentials themselves are never stored in the preference record.

All other registered adapters can be independently enabled or disabled from the same panel. A disabled adapter is omitted from agent tool selection. Unconfigured sources still require valid endpoints, entitlements, and compatible provider response formats; the panel reports readiness but cannot create API access that a provider does not offer.

## Operational limits

- Login and account-setup throttles are process-local; add a shared gateway rate limit before exposing the sign-in endpoint to a large public audience. Marketstack's monthly request budget and provider preferences use shared PostgreSQL when `PROVIDER_PREFERENCES_DATABASE_URL` is configured.
- Set production CORS origins explicitly. Keep login/bootstrap endpoints behind HTTPS and monitor provider quotas at the providers themselves.
- A public Vercel URL makes the application reachable to everyone; authentication limits access to its data and management routes, but this is a single-user application, not a multi-tenant identity system.

## WorldMonitor-inspired research view

The dashboard's headline impact scan groups sourced headlines under geopolitics/trade, rates/policy, energy/commodities, supply chain, natural hazards, and technology/cyber categories, then lists possible exposed industries. It deliberately does not infer incident locations, assign event probabilities, or claim causality from keyword matches. The added feature uses the application's own indexed headline sources; it does not copy WorldMonitor's data or provide its full layer coverage.
