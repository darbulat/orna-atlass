import { expect, test, type Page } from "@playwright/test";

const firstSessionId = "20000000-0000-4000-8000-000000000001";
const secondSessionId = "20000000-0000-4000-8000-000000000002";
const corsHeaders = {
  "Access-Control-Allow-Credentials": "true",
  "Access-Control-Allow-Origin": "http://127.0.0.1:3100",
  "Content-Type": "application/json",
};

async function installFakeAudio(page: Page) {
  await page.addInitScript(() => {
    class FakeAudio extends EventTarget {
      currentTime = 0;
      duration = 3600;
      paused = true;
      src = "";
      ontimeupdate: ((event: Event) => void) | null = null;
      onloadedmetadata: ((event: Event) => void) | null = null;
      ondurationchange: ((event: Event) => void) | null = null;
      onended: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onstalled: ((event: Event) => void) | null = null;

      constructor() {
        super();
        (window as typeof window & { __lastAudio?: FakeAudio }).__lastAudio = this;
      }

      play() {
        this.paused = false;
        return Promise.resolve();
      }

      pause() {
        this.paused = true;
      }

      load() {
        const metadataEvent = new Event("loadedmetadata");
        this.dispatchEvent(metadataEvent);
        this.onloadedmetadata?.(metadataEvent);
        const durationEvent = new Event("durationchange");
        this.dispatchEvent(durationEvent);
        this.ondurationchange?.(durationEvent);
      }

      removeAttribute(name: string) {
        if (name === "src") this.src = "";
      }
    }

    Object.defineProperty(window, "Audio", { configurable: true, value: FakeAudio });
  });
}

function grant(sessionId: string, sequence: number) {
  return {
    session_id: sessionId,
    status: "ready",
    stream_url: `/test-stream/${sessionId}/${sequence}.mp3`,
    expires_at: new Date(Date.now() + 31_000).toISOString(),
    refresh_after_seconds: 1,
  };
}

test("grant refresh preserves playback position and resumes audio", async ({ page }) => {
  await installFakeAudio(page);
  let grantRequests = 0;
  await page.route("**/playback-grants", async (route) => {
    grantRequests += 1;
    await route.fulfill({
      status: 200,
      headers: corsHeaders,
      body: JSON.stringify(grant(firstSessionId, grantRequests)),
    });
  });

  await page.goto("/sessions/first-session");
  await page.getByRole("button", { name: "Play session" }).click();
  await expect(page.getByRole("button", { name: "Pause playback" })).toBeVisible();

  const slider = page.getByRole("slider", { name: "Playback position" });
  await slider.press("ArrowRight");
  await expect(slider).toHaveAttribute("aria-valuenow", "5");
  await expect.poll(() => grantRequests).toBeGreaterThan(1);
  await expect.poll(async () => page.evaluate(() => (
    window as typeof window & { __lastAudio?: { src: string } }
  ).__lastAudio?.src ?? "")).toContain(`/test-stream/${firstSessionId}/2.mp3`);

  const audioState = await page.evaluate(() => {
    const audio = (window as typeof window & {
      __lastAudio?: { currentTime: number; paused: boolean; src: string };
    }).__lastAudio;
    return audio ? { currentTime: audio.currentTime, paused: audio.paused, src: audio.src } : null;
  });
  expect(audioState).toEqual(expect.objectContaining({ currentTime: 5, paused: false }));
  expect(audioState?.src).toContain(`/test-stream/${firstSessionId}/2.mp3`);
});

test("switching sessions aborts a stale grant and ignores its late response", async ({ page }) => {
  await installFakeAudio(page);
  let firstRequestStarted = false;
  let releaseFirstResponse: (() => void) | undefined;
  const firstResponseBarrier = new Promise<void>((resolve) => {
    releaseFirstResponse = resolve;
  });
  await page.route("**/playback-grants", async (route) => {
    if (route.request().url().includes(firstSessionId)) {
      firstRequestStarted = true;
      await firstResponseBarrier;
      await route.fulfill({
        status: 200,
        headers: corsHeaders,
        body: JSON.stringify(grant(firstSessionId, 1)),
      }).catch(() => undefined);
      return;
    }
    await route.fulfill({
      status: 200,
      headers: corsHeaders,
      body: JSON.stringify(grant(secondSessionId, 1)),
    });
  });

  await page.goto("/sessions/first-session");
  await page.getByRole("button", { name: "Play session" }).click({ noWaitAfter: true });
  await expect.poll(() => firstRequestStarted).toBe(true);
  await page.getByRole("link", { name: "Back to atlas" }).click();
  await page.getByRole("button", { name: "Listen", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Pine Marsh" })).toBeVisible();
  await page.getByRole("button", { name: "Play session" }).click();

  await expect(page.getByRole("button", { name: "Pause playback" })).toBeVisible();
  releaseFirstResponse?.();
  await page.waitForTimeout(100);
  const audioSrc = await page.evaluate(() => (
    window as typeof window & { __lastAudio?: { src: string } }
  ).__lastAudio?.src ?? "");
  expect(audioSrc).toContain(secondSessionId);
  await expect(page.getByText("First Session", { exact: true })).toHaveCount(0);
});

test("the playback slider supports keyboard seeking with accessible values", async ({ page }) => {
  await installFakeAudio(page);
  await page.route("**/playback-grants", async (route) => {
    await route.fulfill({ status: 200, headers: corsHeaders, body: JSON.stringify(grant(firstSessionId, 1)) });
  });

  await page.goto("/sessions/first-session");
  const slider = page.getByRole("slider", { name: "Playback position" });
  await slider.focus();
  await slider.press("End");

  await expect(slider).toHaveAttribute("aria-valuemax", "3600");
  await expect(slider).toHaveAttribute("aria-valuenow", "3600");
  await expect(slider).toHaveAttribute("aria-valuetext", "01:00:00");
});
