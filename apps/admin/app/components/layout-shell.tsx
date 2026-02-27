'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import AdminShell from './admin-shell';

export default function LayoutShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === '/login') {
    return <>{children}</>;
  }
  return <AdminShell>{children}</AdminShell>;
}
