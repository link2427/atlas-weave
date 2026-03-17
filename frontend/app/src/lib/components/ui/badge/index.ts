import Badge from './Badge.svelte';
import { tv, type VariantProps } from 'tailwind-variants';

export const badgeVariants = tv({
	base: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider transition-colors',
	variants: {
		variant: {
			default: 'bg-primary/20 text-primary-foreground',
			secondary: 'bg-secondary text-secondary-foreground',
			destructive: 'bg-destructive/20 text-destructive-foreground',
			outline: 'border border-white/15 text-foreground',
			pending: 'bg-[hsl(var(--status-pending))]/15 text-slate-300',
			running: 'bg-[hsl(var(--status-running))]/15 text-teal-200',
			completed: 'bg-[hsl(var(--status-completed))]/15 text-sky-200',
			failed: 'bg-[hsl(var(--status-failed))]/15 text-rose-200',
			skipped: 'bg-[hsl(var(--status-skipped))]/15 text-amber-200',
			cancelled: 'bg-[hsl(var(--status-cancelled))]/15 text-orange-200'
		}
	},
	defaultVariants: {
		variant: 'default'
	}
});

export type BadgeVariant = VariantProps<typeof badgeVariants>['variant'];

export { Badge };
