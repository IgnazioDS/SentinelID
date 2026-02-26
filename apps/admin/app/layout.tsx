import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
import LayoutShell from './components/layout-shell';

export const metadata: Metadata = {
  title: 'SentinelID Admin Ops',
  description: 'SentinelID operations dashboard',
};

export const dynamic = 'force-dynamic';

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LayoutShell>{children}</LayoutShell>
      </body>
    </html>
  );
}
