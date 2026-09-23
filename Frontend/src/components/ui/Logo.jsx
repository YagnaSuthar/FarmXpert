import { Link } from '@/i18n/navigation';
import { cn } from '@/lib/cn';

/** FarmXpert wordmark: serif name, gold X, a sprout for the i-dot of "Xpert". */
export default function Logo({ href = '/', tone = 'default', className }) {
  return (
    <Link href={href} className={cn('group inline-flex items-center gap-2.5', className)} aria-label="FarmXpert">
      <span className={cn('grid size-9 place-items-center rounded-2xl transition-transform duration-300 group-hover:-rotate-6',
        tone === 'light' ? 'bg-white/12 ring-1 ring-white/20' : 'bg-forest')}>
        <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
          <path d="M12 21V11" stroke="#f3e7c9" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M12 12c0-4.2 3-6.6 7-7-0.2 4.2-2.8 7-7 7Z" fill="#b8913a" />
          <path d="M12 14c0-3.4-2.4-5.4-5.8-5.8C6.4 11.6 8.6 14 12 14Z" fill="#6fc083" />
        </svg>
      </span>
      <span className={cn('font-serif text-[1.35rem] leading-none tracking-tight',
        tone === 'light' ? 'text-white' : 'text-forest dark:text-ink')}>
        Farm<span className="text-gold">X</span>pert
      </span>
    </Link>
  );
}
