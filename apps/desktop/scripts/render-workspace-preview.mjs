import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";
import { createServer } from "vite";

const MAX_SLIDE_COUNT = 5_000;
const BASE_RENDER_WIDTH = 960;
const DESKTOP_ROOT = path.resolve(import.meta.dirname, "..");
const SOURCE_ROUTE = "/__workspace_qa__/source.pptx";

const HARNESS_HTML = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; worker-src 'self' blob:; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data: blob:; media-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'">
    <style>html, body { margin: 0; padding: 0; } #stage { position: relative; overflow: hidden; background: #fff; }</style>
  </head>
  <body>
    <div id="stage"></div>
    <script type="module" src="/presentation-preview/visual-compare-entry.ts"></script>
  </body>
</html>`;

function fail(code) {
  process.stdout.write(`${JSON.stringify({ status: "failed", code })}\n`);
  process.exitCode = 1;
}

async function main() {
  const [, , sourceArgument, outputArgument, compatibilityModeArgument] =
    process.argv;
  const compatibilityMode = compatibilityModeArgument ?? "all";
  if (
    !sourceArgument ||
    !outputArgument ||
    process.argv.length > 5 ||
    ![
      "all",
      "all-no-image-effects",
      "baseline",
      "background-only",
      "theme-background-only",
      "theme-override-only",
      "hidden-only",
      "placeholder-only",
      "smartart-only",
      "picture-geometry-only",
    ].includes(compatibilityMode)
  ) {
    fail("PREVIEW_RENDER_ARGUMENTS_INVALID");
    return;
  }

  const sourcePath = path.resolve(sourceArgument);
  const outputDirectory = path.resolve(outputArgument);
  let bytes;
  let browser;
  let server;
  try {
    bytes = await readFile(sourcePath);
    await mkdir(outputDirectory, { recursive: true });
    server = await createServer({
      configFile: path.join(DESKTOP_ROOT, "vite.config.mjs"),
      logLevel: "error",
      server: {
        host: "127.0.0.1",
        port: 0,
        strictPort: false,
        hmr: false,
      },
    });
    await server.listen();
    const address = server.httpServer?.address();
    if (!address || typeof address === "string") {
      throw new Error("PREVIEW_TEST_SERVER_UNAVAILABLE");
    }
    const origin = `http://127.0.0.1:${address.port}`;

    browser = await chromium.launch({
      headless: true,
      args: ["--disable-gpu"],
    });
    const page = await browser.newPage({
      deviceScaleFactor: 1,
      viewport: { width: BASE_RENDER_WIDTH, height: 540 },
    });
    await page.route("**/*", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (requestUrl.protocol === "data:") {
        await route.continue();
        return;
      }
      if (requestUrl.origin !== origin) {
        await route.abort();
        return;
      }
      if (
        requestUrl.pathname === SOURCE_ROUTE &&
        route.request().method() === "GET"
      ) {
        await route.fulfill({
          status: 200,
          contentType:
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
          body: bytes,
        });
        return;
      }
      if (requestUrl.pathname === "/") {
        await route.fulfill({
          status: 200,
          contentType: "text/html; charset=utf-8",
          body: HARNESS_HTML,
        });
        return;
      }
      await route.continue();
    });

    await page.goto(origin, { waitUntil: "load" });
    const slideCount = await page.evaluate(
      (mode) => globalThis.openDeck(mode),
      compatibilityMode,
    );
    const compatibility = await page.evaluate(
      () => globalThis.previewCompatibilityReport,
    );
    if (
      !Number.isSafeInteger(slideCount) ||
      slideCount < 1 ||
      slideCount > MAX_SLIDE_COUNT
    ) {
      fail("PREVIEW_SLIDE_COUNT_INVALID");
      return;
    }

    const slides = [];
    for (let slideNumber = 1; slideNumber <= slideCount; slideNumber += 1) {
      const dimensions = await page.evaluate(
        (currentSlide) => globalThis.renderSlide(currentSlide),
        slideNumber,
      );
      await page.setViewportSize(dimensions);
      const imagePath = path.join(
        outputDirectory,
        `slide-${String(slideNumber).padStart(4, "0")}.png`,
      );
      const png = await page.locator("#stage").screenshot({
        path: imagePath,
        type: "png",
      });
      slides.push({
        ...dimensions,
        png_sha256: createHash("sha256").update(png).digest("hex"),
      });
    }

    const currentBytes = await readFile(sourcePath);
    if (!bytes.equals(currentBytes)) {
      fail("PREVIEW_SOURCE_CHANGED_DURING_RENDER");
      return;
    }
    await writeFile(
      path.join(outputDirectory, "slides.json"),
      JSON.stringify(slides),
    );
    process.stdout.write(
      `${JSON.stringify({
        status: "completed",
        slide_count: slides.length,
        slides,
        compatibility,
        compatibility_mode: compatibilityMode,
      })}\n`,
    );
  } catch (error) {
    const code =
      error instanceof Error ? error.message : "PREVIEW_RENDER_FAILED";
    fail(/^[A-Z0-9_]+$/.test(code) ? code : "PREVIEW_RENDER_FAILED");
  } finally {
    if (browser) await browser.close().catch(() => undefined);
    if (server) await server.close().catch(() => undefined);
  }
}

await main();
