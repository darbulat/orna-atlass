const test = require("node:test");
const assert = require("node:assert/strict");
const { isHlsStream } = require("../../.next-codex-unit/components/audio/playerResources.js");

test("detects HLS manifests without treating legacy audio as HLS", () => {
  assert.equal(isHlsStream("/api/v1/media/hls/id/token/index.m3u8"), true);
  assert.equal(isHlsStream("https://example.test/audio.wav?signature=x"), false);
});
