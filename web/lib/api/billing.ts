import type { components } from "./generated";
import { ApiError, fetchJson } from "./client";
import { apiUrl } from "./sessions";

export type BillingOffer = components["schemas"]["BillingOfferRead"];
export type BillingCheckout = components["schemas"]["CheckoutRead"];
export type BillingPurchase = components["schemas"]["PurchaseRead"];
export type RefundRequest = components["schemas"]["RefundRequestRead"];

export function formatBillingAmount(amountMinor: number, currency: string): string {
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    minimumFractionDigits: 2,
  }).format(amountMinor / 100).replace(/\u00a0/g, " ");
}

function billingRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  return fetchJson<T>(apiUrl(path), { ...init, credentials: "include", headers });
}
export async function fetchBillingOffer(init: RequestInit = {}): Promise<BillingOffer> {
  const offer = await billingRequest<BillingOffer>("/api/v1/billing/offer", init);
  if (
    offer.product_code !== "lifetime_member"
    || !Number.isSafeInteger(offer.amount_minor)
    || offer.amount_minor <= 0
    || !["USD", "KZT"].includes(offer.currency)
    || offer.is_recurring !== false
  ) {
    throw new ApiError("The membership offer is unavailable", { kind: "invalid_response" });
  }
  return offer;
}

export function fetchPurchases(init: RequestInit = {}): Promise<BillingPurchase[]> {
  return billingRequest<BillingPurchase[]>("/api/v1/billing/purchases/me", {
    ...init,
    cache: "no-store",
  });
}

export function createBillingCheckout(idempotencyKey: string): Promise<BillingCheckout> {
  return billingRequest<BillingCheckout>("/api/v1/billing/checkouts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ product_code: "lifetime_member" }),
  });
}

export function requestPurchaseRefund(purchaseId: string): Promise<RefundRequest> {
  return billingRequest<RefundRequest>(
    `/api/v1/billing/purchases/${encodeURIComponent(purchaseId)}/refund-requests`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledge_full_refund: true }),
    },
  );
}
