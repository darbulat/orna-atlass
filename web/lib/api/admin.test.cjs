const assert = require("node:assert/strict");
const test = require("node:test");

const admin = require("../../.next-codex-unit/lib/api/admin.js");

const now = "2026-07-30T10:00:00Z";

const locationFixture = {
  id: "10000000-0000-4000-8000-000000000001",
  name: "Sensitive location",
  slug: "sensitive-location",
  description: null,
  country_code: null,
  region: null,
  habitat: null,
  coordinate_visibility: "hidden_public",
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

const sessionFixture = {
  id: "20000000-0000-4000-8000-000000000001",
  location_id: locationFixture.id,
  slug: "draft-session",
  title: "Draft session",
  publication_status: "draft",
  processing_status: "pending",
  access_level: "public",
  is_featured: false,
  recorded_at: now,
  metadata: {},
  created_at: now,
  updated_at: now,
  revision: '"session-r1"',
};

const collectionFixture = {
  id: "40000000-0000-4000-8000-000000000001",
  slug: "private-collection",
  title: "Private collection",
  description: null,
  is_public: false,
  sort_order: 0,
  metadata: {},
  created_at: now,
  updated_at: now,
  revision: '"collection-r1"',
};

const userFixture = {
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
    status: "inactive",
    plan: "none",
    is_entitled: false,
  },
  revision: '"user-r1"',
};

const auditFixture = {
  id: "70000000-0000-4000-8000-000000000001",
  actor_user_id: null,
  event_type: "location.updated",
  subject_type: "location",
  subject_id: locationFixture.id,
  ip_address: null,
  user_agent: null,
  metadata: {},
  created_at: now,
};

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
  assert.throws(() => admin.parseAdminUserRows({ unexpected: [] }), /Invalid admin list payload/);
  assert.throws(() => admin.parseLocationRows({ items: [] }), /Invalid admin list payload/);
  assert.throws(() => admin.parseLocationRows({ data: [] }), /Invalid admin list payload/);
  const location = { ...locationFixture, coordinate_visibility: "future_visibility" };
  assert.throws(() => admin.parseLocationRows([location]), /Invalid privileged enum/);
  assert.throws(
    () => admin.parseLocationRows([{ ...locationFixture, id: "not-a-uuid" }]),
    /Invalid privileged UUID: location.id/,
  );
  assert.throws(
    () => admin.parseLocationRows([{ ...locationFixture, revision: "" }]),
    /Invalid privileged field: location.revision/,
  );
  assert.throws(
    () => admin.parseSessionRows([{ ...sessionFixture, created_at: "not-a-date" }]),
    /Invalid privileged date-time: session.created_at/,
  );
  assert.throws(
    () => admin.parseAdminUserRows([{ ...userFixture, user: { ...userFixture.user, role: "owner" } }]),
    /Invalid privileged enum/,
  );
  assert.throws(
    () => admin.parseAdminUserRows([{ ...userFixture, user: { ...userFixture.user, email: undefined } }]),
    /Invalid privileged field: user.email/,
  );
  assert.throws(
    () => admin.parseAuditRows([{ ...auditFixture, event_type: "" }]),
    /Invalid privileged field: audit.event_type/,
  );
  assert.throws(
    () => admin.parseLocationRows([{ ...location, coordinate_visibility: "hidden_public", revision: undefined }]),
    /Invalid privileged field: location.revision/,
  );
  assert.throws(() => admin.parseLocationRows([{ ...locationFixture, public_latitude: 91 }]), /location.public_latitude/);
  assert.throws(() => admin.parseLocationRows([{ ...locationFixture, created_at: "2026-02-30T10:00:00Z" }]), /location.created_at/);
  assert.throws(
    () => admin.parseAdminUserRows([{ ...userFixture, user: { ...userFixture.user, email: "not-email" } }]),
    /Invalid privileged email/,
  );
  assert.throws(() => admin.parseAuditRows([{ ...auditFixture, actor_user_id: "not-a-uuid" }]), /audit.actor_user_id/);
  assert.throws(
    () => admin.parseSessionRows([{ ...sessionFixture, media_assets: [{ id: "not-a-uuid" }] }]),
    /session.media_assets\[0\].id/,
  );
});

test("privileged parsers accept generated-contract payloads", () => {
  assert.equal(admin.parseLocationRows([locationFixture])[0].id, locationFixture.id);
  assert.equal(admin.parseSessionRows([sessionFixture])[0].id, sessionFixture.id);
  assert.equal(admin.parseCollectionRows([collectionFixture])[0].id, collectionFixture.id);
  assert.equal(admin.parseAdminUserRows([userFixture])[0].membership_status, "inactive");
  assert.equal(admin.parseAuditRows([auditFixture])[0].id, auditFixture.id);

  const generatedMinimalSession = {
    id: sessionFixture.id,
    location_id: sessionFixture.location_id,
    slug: sessionFixture.slug,
    title: sessionFixture.title,
    recorded_at: sessionFixture.recorded_at,
    metadata: {},
    created_at: now,
    updated_at: now,
    revision: sessionFixture.revision,
    media_assets: [{
      id: "30000000-0000-4000-8000-000000000001",
      session_id: sessionFixture.id,
      kind: "audio",
      mime_type: "audio/mpeg",
      duration_seconds: null,
      size_bytes: null,
      checksum: null,
      metadata: {},
      created_at: now,
    }],
  };
  assert.equal(admin.parseSessionRows([generatedMinimalSession])[0].id, sessionFixture.id);
});

test("every generated required privileged field fails closed when missing", () => {
  const cases = [
    [admin.parseLocationRows, locationFixture, [
      "id", "slug", "name", "description", "country_code", "region", "habitat",
      "exact_latitude", "exact_longitude", "coordinate_visibility", "sensitivity_level",
      "timezone", "metadata", "created_at", "updated_at", "revision",
    ]],
    [admin.parseSessionRows, sessionFixture, [
      "location_id", "slug", "title", "recorded_at", "metadata", "id",
      "created_at", "updated_at", "revision",
    ]],
    [admin.parseCollectionRows, collectionFixture, [
      "id", "slug", "title", "description", "is_public", "sort_order", "metadata",
      "created_at", "updated_at", "revision",
    ]],
    [admin.parseAuditRows, auditFixture, [
      "id", "actor_user_id", "event_type", "subject_type", "subject_id", "ip_address",
      "user_agent", "metadata", "created_at",
    ]],
  ];

  for (const [parser, fixture, required] of cases) {
    for (const field of required) {
      const malformed = { ...fixture };
      delete malformed[field];
      assert.throws(() => parser([malformed]), undefined, `${field} must be required at runtime`);
    }
  }

  for (const field of ["user", "membership", "revision"]) {
    const malformed = { ...userFixture };
    delete malformed[field];
    assert.throws(() => admin.parseAdminUserRows([malformed]), undefined, `${field} must be required at runtime`);
  }
  for (const field of ["id", "email", "email_verified", "role", "is_active", "created_at"]) {
    const malformed = { ...userFixture, user: { ...userFixture.user } };
    delete malformed.user[field];
    assert.throws(() => admin.parseAdminUserRows([malformed]), undefined, `user.${field} must be required at runtime`);
  }
  for (const field of ["user_id", "status", "plan", "is_entitled"]) {
    const malformed = { ...userFixture, membership: { ...userFixture.membership } };
    delete malformed.membership[field];
    assert.throws(() => admin.parseAdminUserRows([malformed]), undefined, `membership.${field} must be required at runtime`);
  }

  const mediaAsset = {
    id: "30000000-0000-4000-8000-000000000001",
    session_id: sessionFixture.id,
    kind: "audio",
    mime_type: "audio/mpeg",
    duration_seconds: null,
    size_bytes: null,
    checksum: null,
    metadata: {},
    created_at: now,
  };
  for (const field of [
    "id", "session_id", "kind", "mime_type", "duration_seconds", "size_bytes",
    "checksum", "metadata", "created_at",
  ]) {
    const malformedAsset = { ...mediaAsset };
    delete malformedAsset[field];
    assert.throws(
      () => admin.parseSessionRows([{ ...sessionFixture, media_assets: [malformedAsset] }]),
      undefined,
      `media_assets[].${field} must be required at runtime`,
    );
  }
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
