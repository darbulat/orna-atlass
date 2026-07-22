"use client";

import Link from "next/link";
import type { ComponentProps, MouseEvent, ReactNode } from "react";

type AnalyticsEventName =
  | "collections_view"
  | "login_opened"
  | "membership_cta_click"
  | "see_all_click"
  | "membership_reserve_click"
  | "subscription_intent"
  | "hero_cta_clicked"
  | "listening_path_selected"
  | "membership_cta_clicked"
  | "final_cta_clicked";

type AnalyticsLinkProps = Omit<ComponentProps<typeof Link>, "children" | "href" | "onClick"> & {
  children: ReactNode;
  destination: string;
  eventName: AnalyticsEventName;
  placement: string;
};

export function AnalyticsLink({
  children,
  destination,
  eventName,
  placement,
  ...linkProps
}: AnalyticsLinkProps) {
  function handleClick(_event: MouseEvent<HTMLAnchorElement>) {
    window.dispatchEvent(
      new CustomEvent("orna:analytics", {
        detail: {
          name: eventName,
          placement,
          destination,
        },
      }),
    );
  }

  return (
    <Link {...linkProps} href={destination} onClick={handleClick}>
      {children}
    </Link>
  );
}
