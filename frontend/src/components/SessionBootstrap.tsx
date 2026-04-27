'use client';

import { useEffect } from 'react';
import { useAuthStore } from '@/lib/auth';

export default function SessionBootstrap() {
  const { bootstrap, hasBootstrapped } = useAuthStore();

  useEffect(() => {
    if (!hasBootstrapped) {
      void bootstrap();
    }
  }, [bootstrap, hasBootstrapped]);

  return null;
}
