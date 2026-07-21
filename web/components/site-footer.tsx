import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div>
        <Link className="site-wordmark" href="/">ORNA Atlas</Link>
        <p>Operated by Kale Ltd. · BIN 221040900084</p>
      </div>
      <nav aria-label="Legal">
        <Link href="/privacy">Privacy Policy</Link>
        <Link href="/terms">Terms</Link>
      </nav>
    </footer>
  );
}
