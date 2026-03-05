/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEMO_MODE?: string;
  readonly VITE_CLOUD_BASE_URL?: string;
  readonly VITE_ADMIN_UI_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
