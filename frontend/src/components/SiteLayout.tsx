import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

interface SiteLayoutProps {
  children: React.ReactNode;
  className?: string;
}

export default function SiteLayout({ children, className = "" }: SiteLayoutProps) {
  return (
    <div className={`min-h-screen flex flex-col ${className}`}>
      <Navbar />
      {children}
      <Footer />
    </div>
  );
}
