import { Link } from 'react-router-dom';
import { Flame, ArrowLeft } from 'lucide-react';

interface AdminLayoutProps {
  children: React.ReactNode;
}

export default function AdminLayout({ children }: AdminLayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 flex h-16 items-center border-b border-border bg-background/80 backdrop-blur-md px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <Link to="/" className="flex items-center gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            返回首页
          </Link>
        </div>
        <div className="absolute left-1/2 flex items-center gap-2 -translate-x-1/2">
          <Flame className="h-5 w-5 text-orange-500" />
          <span className="font-bold">管理后台</span>
        </div>
      </header>
      <main className="p-4 sm:p-6 lg:p-8">{children}</main>
    </div>
  );
}
