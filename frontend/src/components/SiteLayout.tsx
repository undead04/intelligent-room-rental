import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

interface SiteLayoutProps {
  children: React.ReactNode;
  onOpenFilter?: () => void;
  className?: string;
}

export default function SiteLayout({ children, onOpenFilter, className = "" }: SiteLayoutProps) {
  return (
    <div className={`min-h-screen flex flex-col ${className}`}>
      <Navbar onOpenFilter={onOpenFilter} />
      {children}
      <Footer />
    </div>
  );
}
