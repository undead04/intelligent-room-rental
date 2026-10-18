import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

interface SiteLayoutProps {
  children: React.ReactNode;
  className?: string;
  hideFooter?: boolean;
}

export default function SiteLayout({
  children,
  className = "",
  hideFooter = false,
}: SiteLayoutProps) {
  return (
    <div className={`min-h-screen flex flex-col ${className}`}>
      <Navbar />
      {children}
      {!hideFooter && <Footer />}
    </div>
  );
}
