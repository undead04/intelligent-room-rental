import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Homigo - Nền Tảng Tìm Phòng & Nhà Thuê Trí Tuệ Nhân Tạo",
  description: "Homigo Rental Marketplace - Tìm phòng trọ, căn hộ, nhà nguyên căn nhanh chóng, thông minh với AI.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
          rel="stylesheet"
        />
      </head>
      <body className="bg-[#FAF8F4] text-[#121E1A] antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
