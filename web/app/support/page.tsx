import type { Metadata } from "next";
import Link from "next/link";

import { CompanyDetails, LegalPageLayout } from "../../components/legal-page";

export const metadata: Metadata = {
  title: "Support | ORNA Atlas",
  description: "Contact ORNA Atlas about access, purchases, and refunds.",
};

export default function SupportPage() {
  return (
    <LegalPageLayout eyebrow="We are here to help" title="Support" updated="July 30, 2026">
      <section aria-labelledby="support-contact">
        <h2 id="support-contact">Contact us</h2>
        <p>Email <a href="mailto:support@orna.land">support@orna.land</a> for account access, payment status, refund, or listening questions. We aim to acknowledge messages within two business days.</p>
        <p>For a purchase question, include the order reference shown in your ORNA account. Never email card numbers, security codes, Google Pay credentials, passwords, or sign-in links.</p>
      </section>
      <section aria-labelledby="support-purchases">
        <h2 id="support-purchases">Purchases and refunds</h2>
        <p>Payments are completed on Bereke Bank&apos;s hosted checkout. ORNA can confirm access and purchase status but cannot see your payment credentials. Review the <Link href="/refunds">Refund Policy</Link> before requesting a refund.</p>
      </section>
      <section aria-labelledby="support-operator">
        <h2 id="support-operator">Operator details</h2>
        <CompanyDetails />
      </section>
    </LegalPageLayout>
  );
}
