const assert = require("node:assert/strict");
const test = require("node:test");

const interactiveStaticRoutes = [
  "/about",
  "/library",
  "/membership",
  "/privacy",
  "/refunds",
  "/support",
  "/terms",
];

test("interactive static pages disable document caching across frontend deployments", async () => {
  const [{ default: nextConfig }, { PHASE_PRODUCTION_BUILD }] = await Promise.all([
    import("./next.config.mjs"),
    import("next/constants.js"),
  ]);
  const config = nextConfig(PHASE_PRODUCTION_BUILD);
  const headerRules = await config.headers();

  for (const source of interactiveStaticRoutes) {
    const routeRule = headerRules.find((rule) => rule.source === source);
    assert.ok(routeRule, `missing explicit headers for ${source}`);
    assert.ok(
      routeRule.headers.some(
        (header) => header.key.toLowerCase() === "cache-control" && header.value === "no-store",
      ),
      `${source} must use Cache-Control: no-store`,
    );
  }
});
