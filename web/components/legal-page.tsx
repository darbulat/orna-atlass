import { SiteHeader } from "./site-header";

export function LegalPageLayout({
  eyebrow,
  title,
  updated,
  children,
}: {
  eyebrow: string;
  title: string;
  updated: string;
  children: React.ReactNode;
}) {
  return (
    <main className="legal-page" id="main-content">
      <SiteHeader className="legal-nav" />
      <header className="legal-hero">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>Effective and last updated: {updated}</p>
      </header>
      <div className="legal-document">{children}</div>
    </main>
  );
}

export function CompanyDetails({ includeActivities = false }: { includeActivities?: boolean }) {
  return (
    <dl className="legal-company-details">
      <div><dt>Legal entity</dt><dd>Kale Ltd.</dd></div>
      <div><dt>Business Identification Number (BIN)</dt><dd>221040900084</dd></div>
      <div><dt>Registered address</dt><dd>010000, Kazakhstan, Astana, Nura district, 50/3 Turan, office 5</dd></div>
      <div><dt>Chief Executive Officer</dt><dd>Rim Safiullin</dd></div>
      {includeActivities ? (
        <div>
          <dt>Registered business activities</dt>
          <dd>
            <ul>
              <li><span className="legal-activity-code">62011</span><span>Software development</span></li>
              <li><span className="legal-activity-code">62012</span><span>Software maintenance</span></li>
              <li><span className="legal-activity-code">62099</span><span>Other IT services</span></li>
            </ul>
          </dd>
        </div>
      ) : null}
    </dl>
  );
}
