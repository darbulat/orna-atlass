import type { Metadata } from "next";
import Link from "next/link";

import { CompanyDetails, LegalPageLayout } from "../../components/legal-page";

export const metadata: Metadata = {
  title: "Refund Policy | ORNA Atlas",
  description: "Refund terms for ORNA Atlas Lifetime Member Access.",
};

export default function RefundPolicyPage() {
  return (
    <LegalPageLayout eyebrow="Purchase support" title="Refund Policy" updated="July 30, 2026">
      <section aria-labelledby="refund-product">
        <h2 id="refund-product">1. Product covered</h2>
        <p>Lifetime Member Access is a digital service sold for the single price displayed before checkout. During the current test rollout, the Bereke checkout price is KZT 2.00. It has no recurring charge, automatic renewal, physical delivery, or partial billing period.</p>
      </section>
      <section aria-labelledby="refund-eligibility">
        <h2 id="refund-eligibility">2. When you may request a refund</h2>
        <p>You may request a full refund within 14 calendar days after payment. We also accept full refund requests for a duplicate or unauthorized charge, or when paid access was not delivered. We do not issue partial refunds.</p>
      </section>
      <section aria-labelledby="refund-process">
        <h2 id="refund-process">3. How refunds work</h2>
        <p>Sign in to your ORNA account and use the refund action beside the paid purchase, or contact <a href="mailto:support@orna.land">support@orna.land</a>. Include your ORNA purchase reference, but never send card or wallet credentials.</p>
        <p>We aim to process an eligible request within 10 business days. Bereke Bank returns funds to the original payment method; your bank may need additional posting time. Paid access remains available until the provider confirms the refund, then ends unless another valid entitlement applies.</p>
      </section>
      <section aria-labelledby="refund-operator">
        <h2 id="refund-operator">4. Merchant</h2>
        <CompanyDetails />
        <p>Questions may also be submitted through <Link href="/support">Support</Link>.</p>
      </section>
    </LegalPageLayout>
  );
}
