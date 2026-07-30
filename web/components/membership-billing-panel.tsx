"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { apiErrorMessage } from "../lib/api/client";
import {
  createBillingCheckout,
  fetchBillingOffer,
  fetchPurchases,
  requestPurchaseRefund,
  type BillingOffer,
  type BillingPurchase,
} from "../lib/api/billing";

function newIdempotencyKey(): string {
  return `checkout_${crypto.randomUUID().replaceAll("-", "")}`;
}
export function MembershipBillingPanel({ emailVerified }: { emailVerified: boolean }) {
  const [offer, setOffer] = useState<BillingOffer | null>(null);
  const [purchases, setPurchases] = useState<BillingPurchase[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const checkoutKey = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchBillingOffer({ signal: controller.signal, cache: "no-store" }),
      fetchPurchases(),
    ]).then(([nextOffer, nextPurchases]) => {
      if (controller.signal.aborted) return;
      setOffer(nextOffer);
      setPurchases(nextPurchases);
    }).catch((error) => {
      if (!controller.signal.aborted) setMessage(apiErrorMessage(error, "Unable to load billing."));
    });
    return () => controller.abort();
  }, []);

  const latest = purchases?.[0] ?? null;
  const paid = purchases?.find((purchase) => purchase.status === "paid") ?? null;

  async function startCheckout() {
    checkoutKey.current ??= newIdempotencyKey();
    setBusy(true);
    setMessage(null);
    try {
      const checkout = await createBillingCheckout(checkoutKey.current);
      if (!checkout.checkout_url) {
        setMessage("Your checkout is being prepared. Refresh this page before trying again.");
        return;
      }
      window.location.assign(checkout.checkout_url);
    } catch (error) {
      setMessage(apiErrorMessage(error, "Unable to open secure checkout."));
    } finally {
      setBusy(false);
    }
  }

  async function requestRefund() {
    if (!paid) return;
    setBusy(true);
    setMessage(null);
    try {
      await requestPurchaseRefund(paid.id);
      setPurchases((current) => current?.map((purchase) => (
        purchase.id === paid.id ? { ...purchase, status: "refund_requested" } : purchase
      )) ?? null);
      setMessage("Your full refund request was recorded. We will update the status after Bereke Bank confirms it.");
    } catch (error) {
      setMessage(apiErrorMessage(error, "Unable to request a refund."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="billing-panel" aria-labelledby="billing-heading" aria-live="polite">
      <div>
        <p className="eyebrow">Lifetime Member Access</p>
        <h2 id="billing-heading">One payment. No renewal.</h2>
        <p>Permanent access to available members-only recordings for exactly USD $10.00.</p>
      </div>
      <div className="billing-purchase-card">
        <strong>USD $10.00</strong>
        <span>One-time digital purchase · no physical delivery</span>
        {!emailVerified ? <p>Verify your email before opening secure checkout.</p> : null}
        {paid ? (
          <>
            <p><b>Paid:</b> {paid.paid_at ? new Date(paid.paid_at).toLocaleDateString("en") : "Confirmed"}</p>
            <p><b>Order:</b> {paid.merchant_reference}</p>
            <button type="button" disabled={busy} onClick={requestRefund}>Request full refund</button>
          </>
        ) : (
          <button
            type="button"
            disabled={busy || !emailVerified || !offer?.checkout_available}
            onClick={startCheckout}
          >
            {busy ? "Opening…" : offer?.checkout_available ? "Continue to secure payment" : "Checkout unavailable"}
          </button>
        )}
        {latest && !paid ? <p><b>Latest payment:</b> {latest.status.replaceAll("_", " ")}</p> : null}
        <p className="billing-disclosure">
          Payment is processed on Bereke Bank’s hosted checkout. By continuing, you agree to the
          {" "}<Link href="/terms">Terms</Link> and <Link href="/refunds">Refund Policy</Link>.
        </p>
        {message ? <p role="alert">{message}</p> : null}
      </div>
    </section>
  );
}
