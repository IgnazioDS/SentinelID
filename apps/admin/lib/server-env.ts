const DEFAULT_SESSION_TTL_MINUTES = 480;

function requireEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

export interface AdminServerConfig {
  cloudBaseUrl: string;
  adminApiToken: string;
  adminUiUsername: string;
  adminUiPasswordHash: string;
  adminUiSessionSecret: string;
  adminUiSessionTtlMinutes: number;
}

export function getAdminServerConfig(): AdminServerConfig {
  const cloudBaseUrl =
    process.env.CLOUD_BASE_URL?.trim() || process.env.NEXT_PUBLIC_CLOUD_BASE_URL?.trim();
  if (!cloudBaseUrl) {
    throw new Error(
      'Admin configuration missing CLOUD_BASE_URL (or NEXT_PUBLIC_CLOUD_BASE_URL fallback).',
    );
  }

  const ttlRaw = process.env.ADMIN_UI_SESSION_TTL_MINUTES?.trim();
  const parsedTtl = ttlRaw ? Number.parseInt(ttlRaw, 10) : DEFAULT_SESSION_TTL_MINUTES;
  const adminUiSessionTtlMinutes =
    Number.isFinite(parsedTtl) && parsedTtl > 0 ? parsedTtl : DEFAULT_SESSION_TTL_MINUTES;

  return {
    cloudBaseUrl,
    adminApiToken: requireEnv('ADMIN_API_TOKEN'),
    adminUiUsername: requireEnv('ADMIN_UI_USERNAME'),
    adminUiPasswordHash: requireEnv('ADMIN_UI_PASSWORD_HASH'),
    adminUiSessionSecret: requireEnv('ADMIN_UI_SESSION_SECRET'),
    adminUiSessionTtlMinutes,
  };
}
