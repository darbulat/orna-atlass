import Link from "next/link";

import { fetchBillingOffer, formatBillingAmount } from "../lib/api/billing";

export async function LifetimeMembershipOffer() {
  let available = false;
  let price = "Price unavailable";
  try {
    const offer = await fetchBillingOffer({ cache: "no-store" });
    available = offer.checkout_available;
    price = formatBillingAmount(offer.amount_minor, offer.currency);
  } catch {
    // The public page keeps the fixed product disclosure but never invents checkout availability.
  }
  return (
    <section className="lifetime-offer" aria-labelledby="lifetime-offer-heading">
      <div>
        <p className="eyebrow">Lifetime membership</p>
        <h2 id="lifetime-offer-heading">Hear the complete archive for one clear price.</h2>
        <p>
          Permanent access to available members-only field recordings. This is a digital service
          with no physical delivery, recurring charge, or automatic renewal.
        </p>
        <Link href="/refunds">Read the refund policy</Link>
      </div>
      <div className="lifetime-price-card">
        <span>One-time payment</span>
        <strong>{price}</strong>
        <p>Processed securely by Bereke Bank. Available payment methods appear at checkout.</p>
        <Link href="/membership">{available ? "Get lifetime access" : "View membership"}</Link>
      </div>
    </section>
  );
}
