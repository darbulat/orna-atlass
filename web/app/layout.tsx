import type { Metadata } from "next";
import { PlayerProvider } from "../components/audio/PlayerProvider";
import "./styles.css";

export const metadata: Metadata = {
  title: "ORNA Atlas",
  description: "A living sound atlas of natural places.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><PlayerProvider>{children}</PlayerProvider></body>
    </html>
  );
}
