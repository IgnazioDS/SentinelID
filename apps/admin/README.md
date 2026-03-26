# SentinelID Admin

This Next.js app is the Vercel deployment target for the SentinelID admin dashboard.

## Vercel Setup

Create a Vercel project with the repository connected and set the project root directory to `apps/admin`.

Required environment variables:

- `CLOUD_BASE_URL`: Absolute base URL for the SentinelID cloud API. Use the public HTTPS origin in production.
- `ADMIN_API_TOKEN`: Server-side admin token injected by the proxy route.
- `ADMIN_UI_USERNAME`: Login username for the admin dashboard.
- `ADMIN_UI_PASSWORD_HASH` or `ADMIN_UI_PASSWORD_HASH_B64`: Bcrypt hash for the admin password. `ADMIN_UI_PASSWORD_HASH_B64` is the safer option when pasting values into hosted environments.
- `ADMIN_UI_SESSION_SECRET`: Secret used to sign the HttpOnly admin session cookie.

Optional environment variables:

- `ADMIN_UI_SESSION_TTL_MINUTES`: Session duration in minutes. Defaults to `480`.
- `ADMIN_UI_SESSION_SECURE`: Set to `1` in production to force secure cookies. On Vercel this can usually be omitted because HTTPS is detected from forwarded headers.
- `NEXT_PUBLIC_CLOUD_BASE_URL`: Fallback only if `CLOUD_BASE_URL` is not set.

## Local Verification

```bash
npm install
npm run lint
npm run build
```

## Deploy

Recommended monorepo flow:

```bash
cd /path/to/SentinelID
vercel link --repo
```

In the Vercel project settings, set the Root Directory to `apps/admin`. After that, deployments can run from the repository root with the linked project:

```bash
vercel
```

For production:

```bash
vercel --prod
```
