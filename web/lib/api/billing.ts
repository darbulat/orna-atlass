import type { components } from "./generated";
import { ApiError, fetchJson } from "./client";
import { apiUrl } from "./sessions";

export type BillingOffer = components["schemas"]["BillingOfferRead"];
export type BillingCheckout = components["schemas"]["CheckoutRead"];
export type BillingPurchase = components["schemas"]["PurchaseRead"];
export type RefundRequest = components["schemas"]["RefundRequestRead"];

function billingRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  return fetchJson<T>(apiUrl(path), { ...init, credentials: "include", headers });
}
export async function fetchBillingOffer(init: RequestInit = {}): Promise<BillingOffer> {
  const offer = await billingRequest<BillingOffer>("/api/v1/billing/offer", init);
  if (
    offer.product_code !== "lifetime_member"
    || offer.amount_minor !== 1000
    || offer.currency !== "USD"
    || offer.is_recurring !== false
  ) {
    throw new ApiError("The membership offer is unavailable", { kind: "invalid_response" });
  }
  return offer;
}

export function fetchPurchases(): Promise<BillingPurchase[]> {
  return billingRequest<BillingPurchase[]>("/api/v1/billing/purchases/me", { cache: "no-store" });
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
