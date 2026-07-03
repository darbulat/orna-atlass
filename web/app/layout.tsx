import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "ORNA Atlas",
  description: "A living sound atlas of natural places.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
