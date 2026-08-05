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
const CHECKOUT_PENDING_STATUSES = new Set(["creating", "provider_outcome_unknown", "pending"]);

function formatBillingDate(value: string): string | null {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function refundDeadline(value: string): string | null {
  const deadline = new Date(value);
  if (!Number.isFinite(deadline.getTime())) return null;
  deadline.setUTCDate(deadline.getUTCDate() + 14);
  return formatBillingDate(deadline.toISOString());
}

function abbreviateOrderReference(value: string): string {
  if (value.length <= 21) return value;
  return `${value.slice(0, 12)}…${value.slice(-6)}`;
}

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
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [refundConfirming, setRefundConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const checkoutKey = useRef<string | null>(null);
  const refundTrigger = useRef<HTMLButtonElement | null>(null);
  const refundConfirmation = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (refundConfirming) refundConfirmation.current?.focus();
  }, [refundConfirming]);

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
  const purchase = purchases?.find((item) => item.status === "paid" || item.status === "refund_requested") ?? null;
  const paid = purchase?.status === "paid" ? purchase : null;
  const isRefundRequested = purchase?.status === "refund_requested";
  const isTestMode = purchase
    ? purchase.currency === "KZT" && purchase.amount_minor === 200
    : offer?.currency === "KZT" && offer.amount_minor === 200;
  const paidDate = purchase?.paid_at ? formatBillingDate(purchase.paid_at) : null;
  const refundWindowDeadline = purchase?.paid_at ? refundDeadline(purchase.paid_at) : null;

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
            : checkout.status === "provider_outcome_unknown"
              ? "The payment provider response is unresolved. Do not start another payment; refresh for confirmation or contact support."
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

  async function copyOrderReference() {
    if (!purchase) return;
    setCopyMessage(null);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(purchase.merchant_reference);
      setCopyMessage("Order ID copied.");
    } catch {
      setCopyMessage("Unable to copy the order ID.");
    }
  }

  function openRefundConfirmation() {
    setMessage(null);
    setRefundConfirming(true);
  }

  function cancelRefundConfirmation() {
    setRefundConfirming(false);
    window.requestAnimationFrame(() => refundTrigger.current?.focus());
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
      setRefundConfirming(false);
      setMessage("Your refund request was received. We'll update the status when the refund is confirmed.");
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
        <h2 id="billing-heading">
          {purchase
            ? isEntitled === true ? "Lifetime access is active" : "Purchase confirmed"
            : "One payment. No renewal."}
        </h2>
        <p>
          {purchase
            ? isEntitled === true
              ? "Your one-time purchase keeps available members-only recordings unlocked."
              : isEntitled === false
                ? "Membership access is not currently active."
                : "Membership access status is loading."
            : "Permanent access to available members-only recordings for the exact one-time price shown at checkout."}
        </p>
      </div>
      <div className="billing-purchase-card">
        {isTestMode ? (
          <p className="billing-test-mode">
            <strong>Test payment mode</strong>
            <span>This checkout does not indicate production payment readiness.</span>
          </p>
        ) : null}
        {purchase ? (
          <>
            <dl className="billing-purchase-summary" role="group" aria-label="Purchase summary">
              <div><dt>Amount</dt><dd>{formatBillingAmount(purchase.amount_minor, purchase.currency)}</dd></div>
              <div><dt>Paid</dt><dd>{paidDate ?? "Confirmed"}</dd></div>
              <div>
                <dt>Order ID</dt>
                <dd>
                  <span className="billing-order-reference" title={purchase.merchant_reference}>
                    {abbreviateOrderReference(purchase.merchant_reference)}
                  </span>
                  <span
                    className="visually-hidden"
                    id={`billing-order-reference-${purchase.id}`}
                  >
                    Full order ID {purchase.merchant_reference}
                  </span>
                  <button
                    className="billing-copy-order"
                    type="button"
                    aria-label="Copy order ID"
                    aria-describedby={`billing-order-reference-${purchase.id}`}
                    onClick={copyOrderReference}
                  >
                    Copy
                  </button>
                </dd>
              </div>
            </dl>
            {copyMessage ? <p className="billing-copy-status" role="status">{copyMessage}</p> : null}
            {isRefundRequested ? (
              <div className="billing-refund-status">
                <strong>Refund requested</strong>
                <p>Refund confirmation is pending. Your current access status remains visible above.</p>
              </div>
            ) : (
              <>
                <p className="billing-refund-window">
                  {refundWindowDeadline
                    ? `Full refunds can be requested until ${refundWindowDeadline}.`
                    : "Full refunds can be requested within 14 calendar days of payment."}
                </p>
                {refundConfirming ? (
                  <div
                    className="billing-refund-confirmation"
                    role="group"
                    aria-labelledby="billing-refund-confirmation-heading"
                    ref={refundConfirmation}
                    tabIndex={-1}
                  >
                    <h3 id="billing-refund-confirmation-heading">Confirm full refund</h3>
                    <p>
                      Your payment will be refunded in full to the original payment method. Your
                      purchase-backed access will end after the refund is confirmed.
                    </p>
                    <div>
                      <button type="button" disabled={busy} onClick={cancelRefundConfirmation}>
                        Keep membership
                      </button>
                      <button
                        className="billing-refund-confirm"
                        type="button"
                        disabled={busy}
                        onClick={requestRefund}
                      >
                        {busy ? "Requesting…" : "Confirm full refund"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    className="billing-refund-trigger"
                    type="button"
                    disabled={busy}
                    onClick={openRefundConfirmation}
                    ref={refundTrigger}
                  >
                    Request full refund
                  </button>
                )}
              </>
            )}
            <p className="billing-disclosure">
              Refunds are subject to the <Link href="/refunds">Refund Policy</Link>.
            </p>
          </>
        ) : (
          <>
            <strong>
              {offer ? formatBillingAmount(offer.amount_minor, offer.currency) : "Price unavailable"}
            </strong>
            <span>One-time digital purchase · no physical delivery</span>
            {!emailVerified ? <p>Verify your email before opening secure checkout.</p> : null}
            {isEntitled ? (
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
            {latest ? <p><b>Latest payment:</b> {latest.status.replaceAll("_", " ")}</p> : null}
            <p className="billing-disclosure">
              Payment is completed securely on Bereke Bank’s checkout. By continuing, you agree to
              the <Link href="/terms">Terms</Link> and <Link href="/refunds">Refund Policy</Link>.
            </p>
          </>
        )}
        {message ? <p role="alert">{message}</p> : null}
      </div>
    </section>
  );
}
