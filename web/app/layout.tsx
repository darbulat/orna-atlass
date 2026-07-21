import type { Metadata } from "next";
import { AnalyticsBridge } from "../components/analytics-bridge";
import { PlayerProvider } from "../components/audio/PlayerProvider";
import { SiteFooter } from "../components/site-footer";
import "cesium/Build/Cesium/Widgets/widgets.css";
import "./styles.css";

export const metadata: Metadata = {
  title: "ORNA Atlas",
  description: "A living sound atlas of natural places.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <AnalyticsBridge />
        <PlayerProvider>{children}</PlayerProvider>
        <SiteFooter />
      </body>
    </html>
  );
}
