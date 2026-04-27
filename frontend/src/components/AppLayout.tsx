'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  Upload,
  BarChart3,
  FileText,
  LogOut,
  Shield,
  ChevronRight,
  Bell,
  Search,
  Menu,
  X,
  FolderOpen,
} from 'lucide-react';
import { useAuthStore } from '@/lib/auth';
import clsx from 'clsx';

const NAV = [
  { href: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/upload', icon: Upload, label: 'Upload' },
  { href: '/recordings', icon: FolderOpen, label: 'Recordings' },
  { href: '/analytics', icon: BarChart3, label: 'Analytics' },
  { href: '/analyzer', icon: FileText, label: 'Analyzer' },
];

function Navigation({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
      <p className="section-title px-2 mb-3">Navigation</p>
      {NAV.map(({ href, icon: Icon, label }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={clsx('nav-item', active && 'nav-item-active')}
            onClick={onNavigate}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
            {active && <ChevronRight className="w-3.5 h-3.5 ml-auto" />}
          </Link>
        );
      })}
    </nav>
  );
}

function UserCard({
  onLogout,
  isGuestSession,
}: {
  onLogout: () => void;
  isGuestSession: boolean;
}) {
  const { user } = useAuthStore();
  if (!user) return null;
  const displayName = user.name || user.email || 'Workspace User';
  const displayRole = isGuestSession ? 'guest session' : (user.role || 'member');

  return (
    <div className="p-3 border-t border-white/5">
      <div className="flex items-center gap-3 p-3 rounded-xl bg-white/3">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
          {displayName.charAt(0).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-white truncate">{displayName}</div>
          <div className="text-[11px] text-slate-500 truncate capitalize">
            {displayRole}
          </div>
        </div>
        <button onClick={onLogout} className="text-slate-600 hover:text-red-400 transition-colors p-1">
          <LogOut className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { logout, isGuestSession } = useAuthStore();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="hidden lg:flex w-64 flex-shrink-0 flex-col border-r border-white/5 bg-surface-50/80 backdrop-blur-xl">
        <div className="flex items-center gap-3 px-5 py-5 border-b border-white/5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center flex-shrink-0">
            <Shield className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-sm font-bold text-white">AegisCX</div>
            <div className="text-[10px] text-slate-500 font-medium tracking-wider">INTELLIGENCE ENGINE</div>
          </div>
        </div>
        <Navigation pathname={pathname} />
        <UserCard onLogout={logout} isGuestSession={isGuestSession} />
      </aside>

      <AnimatePresence>
        {mobileNavOpen && (
          <>
            <motion.button
              type="button"
              className="lg:hidden fixed inset-0 z-40 bg-black/55"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileNavOpen(false)}
            />
            <motion.aside
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ duration: 0.22 }}
              className="lg:hidden fixed inset-y-0 left-0 z-50 w-72 flex flex-col border-r border-white/5 bg-surface-50/95 backdrop-blur-2xl"
            >
              <div className="flex items-center justify-between gap-3 px-5 py-5 border-b border-white/5">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center flex-shrink-0">
                    <Shield className="w-4 h-4 text-white" />
                  </div>
                  <div>
                    <div className="text-sm font-bold text-white">AegisCX</div>
                    <div className="text-[10px] text-slate-500 font-medium tracking-wider">LOCAL STACK</div>
                  </div>
                </div>
                <button type="button" onClick={() => setMobileNavOpen(false)} className="btn-ghost p-2">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <Navigation pathname={pathname} onNavigate={() => setMobileNavOpen(false)} />
              <UserCard onLogout={logout} isGuestSession={isGuestSession} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <header className="flex items-center justify-between gap-3 px-4 lg:px-6 py-4 border-b border-white/5 bg-surface-50/60 backdrop-blur-xl flex-shrink-0">
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setMobileNavOpen(true)} className="btn-ghost p-2 lg:hidden">
              <Menu className="w-4 h-4" />
            </button>
            <div className="relative hidden md:block">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              <input
                type="text"
                placeholder="Search recordings..."
                className="input-field pl-9 py-2 w-56 lg:w-64 text-sm"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isGuestSession && (
              <span className="hidden sm:inline-flex badge badge-pending">Guest Session</span>
            )}
            <button className="btn-ghost p-2.5 relative">
              <Bell className="w-4 h-4" />
              <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-indigo-400" />
            </button>
            <Link href="/upload" className="btn-primary text-sm">
              <Upload className="w-4 h-4" /> Upload
            </Link>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 lg:p-6">
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            {children}
          </motion.div>
        </div>
      </main>
    </div>
  );
}
