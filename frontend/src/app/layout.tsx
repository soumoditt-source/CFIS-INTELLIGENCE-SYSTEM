import type { Metadata } from 'next';
import './globals.css';
import { Toaster } from 'react-hot-toast';
import SessionBootstrap from '@/components/SessionBootstrap';

export const metadata: Metadata = {
  title: { default: 'CFIS | Customer Feedback Intelligence System', template: '%s | CFIS' },
  description: 'Enterprise Customer Intelligence built with Next.js 14, FastAPI and Agentic Models.',
  keywords: ['customer feedback', 'sentiment analysis', 'AI transcription', 'customer intelligence', 'NLP', 'behavioral analytics'],
  authors: [{ name: 'AegisCX Engineering' }],
  openGraph: {
    title: 'CFIS | Customer Feedback Intelligence System',
    description: 'Enterprise Customer Intelligence built with Next.js 14, FastAPI and Agentic Models.',
    type: 'website',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body className="antialiased">
        <SessionBootstrap />
        <div className="aurora-bg" aria-hidden="true" />
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: 'rgba(20,23,32,0.95)',
              color: '#f1f5f9',
              border: '1px solid rgba(99,102,241,0.3)',
              borderRadius: '12px',
              backdropFilter: 'blur(16px)',
              fontSize: '14px',
            },
            success: { iconTheme: { primary: '#10b981', secondary: '#f1f5f9' } },
            error:   { iconTheme: { primary: '#ef4444', secondary: '#f1f5f9' } },
          }}
        />
      </body>
    </html>
  );
}
