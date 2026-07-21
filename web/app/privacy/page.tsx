import type { Metadata } from "next";
import Link from "next/link";

import { CompanyDetails, LegalPageLayout } from "../../components/legal-page";

export const metadata: Metadata = {
  title: "Privacy Policy | ORNA Atlas",
  description: "How ORNA Atlas collects, uses, protects, and shares personal data.",
};

export default function PrivacyPage() {
  return (
    <LegalPageLayout eyebrow="Your data and choices" title="Privacy Policy" updated="July 21, 2026">
      <section aria-labelledby="privacy-controller">
        <h2 id="privacy-controller">1. Who controls your data</h2>
        <p>
          Kale Ltd. (“Kale”, “ORNA Atlas”, “we”, “us”) operates ORNA Atlas and is the
          controller of personal data described in this policy.
        </p>
        <CompanyDetails />
      </section>

      <section aria-labelledby="privacy-scope">
        <h2 id="privacy-scope">2. Scope</h2>
        <p>
          This policy applies when you visit ORNA Atlas, create or use an account, sign in
          through an identity provider, explore the atlas, listen to recordings, or contact us.
          Third-party services have their own privacy terms.
        </p>
      </section>

      <section aria-labelledby="privacy-data">
        <h2 id="privacy-data">3. Data we collect</h2>
        <h3>Data you provide</h3>
        <ul>
          <li>Your e-mail address and account credentials. Passwords are stored only as secure hashes, not in readable form.</li>
          <li>Information you send when making a privacy, legal, or support request.</li>
        </ul>
        <h3>Account and service data</h3>
        <ul>
          <li>Account identifiers, roles, membership entitlements, sign-in and refresh-session records.</li>
          <li>If you choose social sign-in, the provider, provider account identifier, verified e-mail address, and authentication results needed to sign you in.</li>
          <li>Playback grants and security/audit events needed to protect restricted recordings and accounts.</li>
        </ul>
        <h3>Technical and usage data</h3>
        <ul>
          <li>IP address, user agent, request time, bounded route information, error and security logs.</li>
          <li>Limited conversion events such as starting a sample, listening milestones, and selecting an atlas or membership link. These events use predefined names and placements rather than free-form personal content.</li>
          <li>Essential cookies or similar storage used for secure sign-in, refresh sessions, and service operation.</li>
        </ul>
        <h3>Location</h3>
        <p>
          If you activate “Use current location”, your browser asks for permission and uses the
          coordinates to select the nearest public listening site. This calculation happens in
          your browser; ORNA Atlas does not add your device location to your account. Recording
          locations shown publicly may be generalized or withheld to protect sensitive habitats.
        </p>
      </section>

      <section aria-labelledby="privacy-uses">
        <h2 id="privacy-uses">4. How and why we use data</h2>
        <ul>
          <li>To provide accounts, authentication, atlas discovery, membership access, and protected playback.</li>
          <li>To secure the service, prevent abuse, investigate incidents, and keep necessary audit records.</li>
          <li>To understand whether core listening and registration journeys work and to improve ORNA Atlas.</li>
          <li>To respond to requests and comply with applicable legal obligations.</li>
        </ul>
        <p>
          Depending on the context and applicable law, we process data to perform our agreement
          with you, pursue legitimate interests in operating and securing the service, comply with
          law, or act on your consent where consent is required. You can withdraw consent without
          affecting earlier lawful processing.
        </p>
      </section>

      <section aria-labelledby="privacy-sharing">
        <h2 id="privacy-sharing">5. When data is shared</h2>
        <p>We do not sell personal data. Personal data may be processed or received by:</p>
        <ul>
          <li>infrastructure, hosting, storage, monitoring, and other processors that operate the service for us;</li>
          <li>Google, Apple, or Facebook when you choose that provider for sign-in;</li>
          <li>professional advisers, authorities, or other parties when required by law or needed to establish, exercise, or defend legal claims; or</li>
          <li>a successor in a merger, reorganization, or transfer, subject to appropriate safeguards.</li>
        </ul>
        <h3>Map imagery provider</h3>
        <p>
          When you open the interactive atlas, your browser may request ArcGIS World Imagery
          tiles directly from Esri. As the recipient of that request, Esri ordinarily receives
          your IP address, user agent, and request metadata and processes that information under
          its own privacy terms. Kale does not control Esri’s independent processing.
        </p>
      </section>

      <section aria-labelledby="privacy-transfers">
        <h2 id="privacy-transfers">6. International processing</h2>
        <p>
          Providers may process data outside Kazakhstan or your country. Where required, we use
          contractual or other legally recognized safeguards and limit transfers to what is
          necessary for the purposes above.
        </p>
      </section>

      <section aria-labelledby="privacy-retention">
        <h2 id="privacy-retention">7. Retention and security</h2>
        <p>
          We retain personal data only for as long as needed to provide the service, secure it,
          resolve disputes, and meet legal obligations. Retention periods depend on the type of
          record and why it is held. We use technical and organizational safeguards, including
          access controls, password hashing, short-lived access credentials, rotating sessions,
          and restricted media grants. No internet service can guarantee absolute security.
        </p>
      </section>

      <section aria-labelledby="privacy-rights">
        <h2 id="privacy-rights">8. Your privacy rights</h2>
        <p>
          Subject to applicable law, you may ask to access, correct, update, delete, restrict, or
          receive a copy of your personal data; object to certain processing; withdraw consent;
          and complain to the competent data-protection authority. Some records may be retained
          where law or security obligations require it.
        </p>
        <p>
          Send a signed request identifying your account and request to our registered address
          above. We may verify your identity before acting. We will not ask for your password.
        </p>
      </section>

      <section aria-labelledby="privacy-children">
        <h2 id="privacy-children">9. Children</h2>
        <p>
          ORNA Atlas is not directed to children under 16, and we do not knowingly create accounts
          for them. A parent or guardian who believes a child provided personal data should contact us.
        </p>
      </section>

      <section aria-labelledby="privacy-changes">
        <h2 id="privacy-changes">10. Changes to this policy</h2>
        <p>
          We may update this policy as the service or law changes. The date above identifies the
          current version. Material changes may also be presented through the service when appropriate.
        </p>
        <p>Use of ORNA Atlas is also governed by our <Link href="/terms">Terms of Use</Link>.</p>
      </section>
    </LegalPageLayout>
  );
}
