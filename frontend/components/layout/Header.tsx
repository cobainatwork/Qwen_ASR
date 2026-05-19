import Link from 'next/link';

export function Header() {
  return (
    <header className="glass-card mx-4 mt-4 px-6 py-4 flex items-center justify-between">
      <Link href="/" className="text-xl font-semibold">Qwen3-ASR</Link>
      <nav className="flex gap-4 text-sm">
        <Link href="/" className="hover:text-accent">辨識</Link>
        <Link href="/youtube" className="hover:text-accent">YouTube</Link>
        <Link href="/history" className="hover:text-accent">歷史</Link>
        <Link href="/keys" className="hover:text-accent">金鑰</Link>
      </nav>
    </header>
  );
}
