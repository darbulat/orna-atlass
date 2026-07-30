const assert = require("node:assert/strict");
const test = require("node:test");

const admin = require("../../.next-codex-unit/lib/api/admin.js");

const now = "2026-07-30T10:00:00Z";

test("admin user parser accepts the exact nested user and membership contract", () => {
  const [row] = admin.parseAdminUserRows([{
    user: {
      id: "50000000-0000-4000-8000-000000000001",
      email: "admin@example.test",
      email_verified: true,
      role: "admin",
      is_active: true,
      created_at: now,
    },
    membership: {
      user_id: "50000000-0000-4000-8000-000000000001",
      status: "active",
      plan: "member",
      is_entitled: true,
    },
    revision: '"user-r1"',
  }]);

  assert.equal(row.id, "50000000-0000-4000-8000-000000000001");
  assert.equal(row.email, "admin@example.test");
  assert.equal(row.membership_status, "active");
  assert.equal(row.revision, '"user-r1"');
});

test("privileged parsers fail closed on malformed envelopes and unknown enums", () => {
  assert.throws(() => admin.parseAdminUserRows({ unexpected: [] }), /Invalid admin list envelope/);
  const location = {
    id: "50000000-0000-4000-8000-000000000002",
    name: "Sensitive location",
    slug: "sensitive-location",
    description: null,
    country_code: null,
    region: null,
    habitat: null,
    coordinate_visibility: "future_visibility",
    sensitivity_level: "protected",
    exact_latitude: 1.23,
    exact_longitude: 4.56,
    public_latitude: null,
    public_longitude: null,
    timezone: "UTC",
    metadata: {},
    archived_at: null,
    created_at: now,
    updated_at: now,
    revision: '"location-r1"',
  };
  assert.throws(() => admin.parseLocationRows([location]), /Invalid privileged enum/);
  assert.throws(
    () => admin.parseLocationRows([{ ...location, coordinate_visibility: "hidden_public", revision: undefined }]),
    /Invalid privileged field: location.revision/,
  );
});

test("admin URL builder includes only explicitly supplied bounded filters", () => {
  const url = admin.buildAdminUrl("/api/v1/admin/users", {
    role: "admin",
    limit: "50",
    offset: "0",
  });
  assert.equal(url, "/api/v1/admin/users?role=admin&limit=50&offset=0");
  assert.equal(url.includes("email"), false);
  assert.equal(url.includes("operation_log"), false);
});
