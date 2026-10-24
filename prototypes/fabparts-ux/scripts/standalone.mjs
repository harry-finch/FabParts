// Self-contained preview for environments where a local web server is unavailable.
import { readFile, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
let html = await readFile(resolve(root, "dist/index.html"), "utf8");
const jsPath = html.match(
  /<script type="module" crossorigin src="([^"]+)"><\/script>/,
)[1];
const cssPath = html.match(
  /<link rel="stylesheet" crossorigin href="([^"]+)">/,
)[1];
let js = await readFile(resolve(root, "dist" + jsPath), "utf8");
let css = await readFile(resolve(root, "dist" + cssPath), "utf8");
for (const font of [
  ...new Set([...css.matchAll(/url\(([^)]+\.woff2)\)/g)].map((m) => m[1])),
]) {
  const bytes = await readFile(resolve(root, "dist" + font));
  css = css.replaceAll(
    font,
    `data:font/woff2;base64,${bytes.toString("base64")}`,
  );
}
const logo =
  "data:image/svg+xml;base64," +
  (await readFile(resolve(root, "public/logo.svg"))).toString("base64");
js = js.replaceAll("/logo.svg", logo);
html = html
  .replace(
    /<script type="module" crossorigin src="[^"]+"><\/script>/,
    () =>
      `<script type="module">${js.replaceAll("</script", "<\\/script")}</script>`,
  )
  .replace(
    /<link rel="stylesheet" crossorigin href="[^"]+">/,
    () => `<style>${css}</style>`,
  )
  .replace("/logo.svg", logo);
await writeFile(resolve(root, "dist/preview.html"), html);
console.log("Created dist/preview.html (offline, no server required)");
