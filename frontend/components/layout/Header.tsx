import Link from 'next/link';
import { Cpu, ListOrdered } from 'lucide-react';

export function Header() {
  return (
    <header className="app-header">
      <Link
        href="/"
        className="flex items-center gap-2 font-semibold text-base mr-auto cursor-pointer hover:scale-[1.02] transition-transform duration-200"
      >
        <span className="inline-block w-2 h-2 rounded-full bg-accent" aria-hidden />
        Qwen3-ASR
      </Link>
      <div className="flex items-center gap-4 text-xs text-foreground/70">
        <span className="flex items-center gap-1.5" aria-label="GPU 狀態">
          <Cpu className="w-3.5 h-3.5" />
          <span>GPU</span>
          <span className="text-foreground/40">—</span>
        </span>
        <span className="flex items-center gap-1.5" aria-label="佇列狀態">
          <ListOrdered className="w-3.5 h-3.5" />
          <span>佇列</span>
          <span className="text-foreground/40">—</span>
        </span>
      </div>
    </header>
  );
}
