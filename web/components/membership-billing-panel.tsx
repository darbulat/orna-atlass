"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { apiErrorMessage } from "../lib/api/client";
import {
  createBillingCheckout,
  fetchBillingOffer,
  fetchPurchases,
  formatBillingAmount,
  requestPurchaseRefund,
  type BillingOffer,
  type BillingPurchase,
} from "../lib/api/billing";

function newIdempotencyKey(): string {
  return `checkout_${crypto.randomUUID().replaceAll("-", "")}`;
}

const PAYMENT_POLL_INTERVAL_MS = 1_500;
const CHECKOUT_PENDING_STATUSES = new Set(["creating", "pending"]);

type MembershipBillingPanelProps = {
  emailVerified: boolean;
  isEntitled: boolean | null;
  onMembershipRefresh: () => Promise<boolean | null>;
};

export function MembershipBillingPanel({
  emailVerified,
  isEntitled,
  onMembershipRefresh,
}: MembershipBillingPanelProps) {
  const [offer, setOffer] = useState<BillingOffer | null>(null);
  const [purchases, setPurchases] = useState<BillingPurchase[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const checkoutKey = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let pollTimer: number | null = null;
    const returnReference = new URLSearchParams(window.location.search).get("payment_return");

    const clearReturnMarker = () => {
      const params = new URLSearchParams(window.location.search);
      params.delete("payment_return");
      const query = params.toString();
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`,
      );
    };

    const loadPurchases = async () => {
      try {
        const nextPurchases = await fetchPurchases({ signal: controller.signal });
        if (controller.signal.aborted) return;
        setPurchases(nextPurchases);
        if (!returnReference) return;

        const returnedPurchase = nextPurchases.find(
          (purchase) => purchase.merchant_reference === returnReference,
        );
        await onMembershipRefresh();
        if (controller.signal.aborted) return;
        if (returnedPurchase && !CHECKOUT_PENDING_STATUSES.has(returnedPurchase.status)) {
          clearReturnMarker();
          if (returnedPurchase.status === "paid") {
            setMessage("Payment confirmed. Lifetime access is active.");
          } else {
            setMessage(`Payment status: ${returnedPurchase.status.replaceAll("_", " ")}.`);
          }
          return;
        }
        pollTimer = window.setTimeout(() => void loadPurchases(), PAYMENT_POLL_INTERVAL_MS);
      } catch (error) {
        if (!controller.signal.aborted) {
          setMessage(apiErrorMessage(error, "Unable to refresh payment status."));
        }
      }
    };

    void fetchBillingOffer({ signal: controller.signal, cache: "no-store" })
      .then((nextOffer) => {
        if (!controller.signal.aborted) setOffer(nextOffer);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setMessage(apiErrorMessage(error, "Unable to load billing."));
        }
      });
    void loadPurchases();
    return () => {
      controller.abort();
      if (pollTimer !== null) window.clearTimeout(pollTimer);
    };
  }, [onMembershipRefresh]);

  const latest = purchases?.[0] ?? null;
  const paid = purchases?.find((purchase) => purchase.status === "paid") ?? null;

  async function startCheckout() {
    checkoutKey.current ??= newIdempotencyKey();
    setBusy(true);
    setMessage(null);
    try {
      const checkout = await createBillingCheckout(checkoutKey.current);
      if (!checkout.checkout_url) {
        checkoutKey.current = null;
        setMessage(
          checkout.status === "expired"
            ? "That checkout expired. Try again to open a new secure checkout."
            : "Your checkout is being prepared. Refresh this page before trying again.",
        );
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
        <p>
          Permanent access to available members-only recordings for the exact one-time price shown
          at checkout.
        </p>
      </div>
      <div className="billing-purchase-card">
        <strong>
          {offer ? formatBillingAmount(offer.amount_minor, offer.currency) : "Price unavailable"}
        </strong>
        {offer?.currency === "KZT" && offer.amount_minor === 200 ? (
          <span>Test checkout price</span>
        ) : null}
        <span>One-time digital purchase · no physical delivery</span>
        {!emailVerified ? <p>Verify your email before opening secure checkout.</p> : null}
        {paid ? (
          <>
            <p><b>Paid:</b> {paid.paid_at ? new Date(paid.paid_at).toLocaleDateString("en") : "Confirmed"}</p>
            <p><b>Order:</b> {paid.merchant_reference}</p>
            <button type="button" disabled={busy} onClick={requestRefund}>Request full refund</button>
          </>
        ) : isEntitled ? (
          <p><b>Access:</b> Lifetime access is already active on this account.</p>
        ) : (
          <button
            type="button"
            disabled={busy || !emailVerified || isEntitled === null || !offer?.checkout_available}
            onClick={startCheckout}
          >
            {busy
              ? "Opening…"
              : isEntitled === null
                ? "Access status unavailable"
                : offer?.checkout_available
                  ? "Continue to secure payment"
                  : "Checkout unavailable"}
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
