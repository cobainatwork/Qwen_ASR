'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Headphones,
  History,
  Wrench,
  FileEdit,
  Database,
  GraduationCap,
  Hash,
  Youtube,
  Activity,
  KeyRound,
} from 'lucide-react';

import { isVendor } from '@/lib/config';

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

const ALWAYS_VISIBLE: NavItem[] = [
  { href: '/', label: '離線辨識', icon: Headphones },
  { href: '/history', label: '辨識歷史', icon: History },
];

const VENDOR_ONLY: NavItem[] = [
  { href: '/finetune/correction', label: '校正工作台', icon: FileEdit },
  { href: '/finetune/datasets', label: '資料集管理', icon: Database },
  { href: '/finetune/training', label: '訓練管理', icon: GraduationCap },
  { href: '/finetune/hotwords', label: 'Hotword', icon: Hash },
  { href: '/youtube', label: 'YouTube', icon: Youtube },
];

const TAIL: NavItem[] = [
  { href: '/quality', label: '質檢管理', icon: Activity },
  { href: '/keys', label: 'API 金鑰', icon: KeyRound },
];

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={`flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all duration-200 cursor-pointer hover:scale-[1.02] hover:bg-glass-100 focus:outline-none focus:ring-2 focus:ring-accent/50 ${
        active ? 'bg-glass-100 text-accent font-medium' : 'text-foreground/80'
      }`}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      <span>{item.label}</span>
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  return (
    <aside className="app-sidebar">
      <nav aria-label="主選單" className="flex flex-col gap-1 p-3">
        {ALWAYS_VISIBLE.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item.href)} />
        ))}

        {isVendor && (
          <div className="mt-2">
            <div className="flex items-center gap-2 px-3 py-1.5 text-xs uppercase tracking-wide text-foreground/50">
              <Wrench className="w-3 h-3" />
              <span>Fine-tune</span>
            </div>
            {VENDOR_ONLY.map((item) => (
              <NavLink key={item.href} item={item} active={isActive(item.href)} />
            ))}
          </div>
        )}

        <div className="mt-2 pt-2 border-t border-white/40">
          {TAIL.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item.href)} />
          ))}
        </div>
      </nav>
    </aside>
  );
}
