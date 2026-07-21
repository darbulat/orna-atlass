import type { Metadata } from "next";
import Link from "next/link";

import { CompanyDetails, LegalPageLayout } from "../../components/legal-page";

export const metadata: Metadata = {
  title: "Terms of Use | ORNA Atlas",
  description: "Terms that apply when you access or use ORNA Atlas.",
};

export default function TermsPage() {
  return (
    <LegalPageLayout eyebrow="Rules for using the atlas" title="Terms of Use" updated="July 21, 2026">
      <section aria-labelledby="terms-operator">
        <h2 id="terms-operator">1. Operator and agreement</h2>
        <p>
          These Terms of Use (“Terms”) form an agreement between you and Kale Ltd. (“Kale”,
          “ORNA Atlas”, “we”, “us”). By accessing or using ORNA Atlas, you agree to these Terms
          and our <Link href="/privacy">Privacy Policy</Link>. If you do not agree, do not use the service.
        </p>
        <CompanyDetails includeActivities />
      </section>

      <section aria-labelledby="terms-service">
        <h2 id="terms-service">2. The service</h2>
        <p>
          ORNA Atlas is a map-first archive and listening service for field recordings associated
          with real landscapes. It may provide public previews, account features, member-only
          sessions, automated annotations, and editorial information. Features and availability
          may change as the archive develops.
        </p>
        <p>
          Automated analysis, including bird-activity annotations, may be incomplete or incorrect
          and is provided for discovery rather than scientific, safety, or conservation decisions.
          Public coordinates may be generalized or omitted to protect habitats and species.
        </p>
      </section>

      <section aria-labelledby="terms-accounts">
        <h2 id="terms-accounts">3. Accounts</h2>
        <ul>
          <li>You must provide accurate information and be at least 16 years old, or meet the higher minimum age required where you live.</li>
          <li>You are responsible for your credentials and activity under your account. Notify us promptly if you suspect unauthorized use.</li>
          <li>You may not share, sell, transfer, or automate access to an account or protected playback grant.</li>
          <li>Social sign-in is also subject to the chosen provider’s terms.</li>
        </ul>
      </section>

      <section aria-labelledby="terms-membership">
        <h2 id="terms-membership">4. Membership and payment</h2>
        <p>
          ORNA Atlas currently offers early account access and does not initiate public paid
          checkout on the website. If paid plans are introduced, the price, billing period,
          renewal, cancellation, and refund terms will be shown before you purchase. No payment
          obligation arises merely from creating an early-access account.
        </p>
      </section>

      <section aria-labelledby="terms-license">
        <h2 id="terms-license">5. Our rights and third-party content</h2>
        <p>
          Kale and the relevant rights holders retain their respective rights in the ORNA Atlas
          software, design, text, recordings, annotations, trademarks, maps, imagery, and other
          materials. Third-party maps, imagery, software, and content remain the property of their
          respective owners and may be subject to separate notices or licence terms. These Terms do
          not transfer ownership to you. To the extent Kale is authorized to do so, we grant you a
          limited, personal, non-exclusive, non-transferable, revocable right to access and use the
          service for lawful, non-commercial listening and exploration in accordance with these Terms.
        </p>
        <p>Unless we give written permission, you must not:</p>
        <ul>
          <li>copy, download, record, redistribute, broadcast, sell, sublicense, or create derivative datasets from recordings or other content;</li>
          <li>scrape, crawl, bulk-export, train a model on, or systematically extract the service or its data;</li>
          <li>circumvent access, playback, location-protection, rate-limit, or security controls;</li>
          <li>reverse engineer the service except to the limited extent the law does not allow that restriction; or</li>
          <li>remove ownership notices or imply endorsement by Kale, contributors, or recording partners.</li>
        </ul>
      </section>

      <section aria-labelledby="terms-conduct">
        <h2 id="terms-conduct">6. Acceptable conduct</h2>
        <p>
          Do not misuse ORNA Atlas, interfere with its operation, probe it without authorization,
          upload malicious code, impersonate another person, infringe rights, break applicable
          law, or use atlas information to disturb wildlife, enter restricted land, or reveal a
          protected recording location.
        </p>
      </section>

      <section aria-labelledby="terms-third-party">
        <h2 id="terms-third-party">7. Third-party services</h2>
        <p>
          Maps, identity providers, links, and infrastructure may be supplied by third parties.
          Their services are governed by their own terms. We are not responsible for third-party
          services that we do not control.
        </p>
      </section>

      <section aria-labelledby="terms-availability">
        <h2 id="terms-availability">8. Availability and changes</h2>
        <p>
          We may maintain, change, suspend, or discontinue any part of ORNA Atlas. We do not
          promise uninterrupted or error-free availability, that every recording or annotation
          will remain available, or that the service will meet a particular purpose. We may limit
          or suspend access where reasonably necessary for security, legal compliance, or misuse.
        </p>
      </section>

      <section aria-labelledby="terms-disclaimers">
        <h2 id="terms-disclaimers">9. Disclaimers and liability</h2>
        <p>
          To the maximum extent permitted by law, ORNA Atlas is provided “as is” and “as available”,
          without implied warranties of merchantability, fitness for a particular purpose, or
          non-infringement. Nothing in these Terms excludes a warranty or right that cannot lawfully
          be excluded.
        </p>
        <p>
          To the maximum extent permitted by law, Kale is not liable for indirect, incidental,
          special, consequential, or punitive loss, loss of data, profit, goodwill, or opportunity,
          or harm caused by relying on approximate coordinates or automated annotations. Any
          liability that cannot be excluded is limited only to the extent the applicable law allows.
        </p>
      </section>

      <section aria-labelledby="terms-indemnity">
        <h2 id="terms-indemnity">10. Responsibility for misuse</h2>
        <p>
          To the extent permitted by law, you are responsible for losses and reasonable costs
          arising from your unlawful use of ORNA Atlas, violation of these Terms, or infringement
          of another person’s rights.
        </p>
      </section>

      <section aria-labelledby="terms-law">
        <h2 id="terms-law">11. Governing law and disputes</h2>
        <p>
          These Terms are governed by the laws of the Republic of Kazakhstan, without regard to
          conflict-of-law rules. Courts with jurisdiction in Astana, Kazakhstan will hear disputes,
          except where mandatory consumer law gives you the right to bring a claim elsewhere.
          Before filing a claim, please send written notice to our registered address and allow a
          reasonable opportunity to resolve the issue informally.
        </p>
      </section>

      <section aria-labelledby="terms-general">
        <h2 id="terms-general">12. General</h2>
        <p>
          If a provision is unenforceable, the remaining Terms continue in effect. A delay in
          enforcing a right is not a waiver. You may not assign this agreement without our consent;
          we may assign it as part of a business reorganization or transfer. These Terms and the
          Privacy Policy are the entire agreement concerning your use of ORNA Atlas unless separate
          written terms apply.
        </p>
      </section>

      <section aria-labelledby="terms-changes">
        <h2 id="terms-changes">13. Changes and contact</h2>
        <p>
          We may update these Terms to reflect service or legal changes. The date above identifies
          the current version. If a material change requires notice or consent, we will provide it
          as required by law. Legal notices may be sent to Kale Ltd. at the registered address in
          section 1.
        </p>
      </section>
    </LegalPageLayout>
  );
}
