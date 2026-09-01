import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AG-UI Learning Lab",
  description: "Interaktive Full-Stack-Lernanwendung für das AG-UI-Protokoll",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
