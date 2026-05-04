import { CATEGORY_LABELS, type Category } from '@/types';
import { cn } from '@/lib/utils';

interface CategoryFilterProps {
  active: Category;
  onChange: (c: Category) => void;
}

const categories: Category[] = ['all', 'tech', 'finance', 'social', 'global', 'other'];

export default function CategoryFilter({ active, onChange }: CategoryFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {categories.map((cat) => (
        <button
          key={cat}
          onClick={() => onChange(cat)}
          className={cn(
            'rounded-full px-4 py-1.5 text-sm font-medium transition-all duration-200',
            active === cat
              ? 'bg-primary text-primary-foreground shadow-lg'
              : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
          )}
        >
          {CATEGORY_LABELS[cat]}
        </button>
      ))}
    </div>
  );
}
