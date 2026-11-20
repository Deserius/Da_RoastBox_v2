#!/usr/bin/env node
// Low-memory production preview. Build frontend first, then run from any cwd.
// Same-origin /api proxy keeps session/media auth intact, including downloads.
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(process.env.FRONTEND_BUILD_DIR || path.join(__dirname, "../frontend/build"));
const upstream = new URL(process.env.API_PROXY_TARGET || "http://127.0.0.1:8001");
const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || "0.0.0.0";
const types = { ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
  ".ico": "image/x-icon", ".ttf": "font/ttf", ".woff2": "font/woff2", ".mp3": "audio/mpeg", ".mp4": "video/mp4", ".txt": "text/plain; charset=utf-8" };
if (!fs.existsSync(path.join(root, "index.html"))) {
  console.error("Frontend build missing. Run `cd frontend && corepack yarn build` first.");
  process.exit(1);
}
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://preview");
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
    const proxy = http.request({ hostname: upstream.hostname, port: upstream.port || 80,
      path: req.url, method: req.method, headers: { ...req.headers, host: upstream.host } }, (response) => {
      res.writeHead(response.statusCode, response.headers);
      response.pipe(res);
    });
    proxy.setTimeout(300000, () => proxy.destroy(new Error("API timeout")));
    proxy.on("error", () => {
      if (!res.headersSent) res.writeHead(502, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify({ detail: "API is restarting. Please retry shortly." }));
    });
    req.on("aborted", () => proxy.destroy());
    req.pipe(proxy);
    return;
  }
  if (!["GET", "HEAD"].includes(req.method)) { res.writeHead(405).end(); return; }
  let pathname;
  try { pathname = decodeURIComponent(url.pathname); } catch { res.writeHead(400).end(); return; }
  let file = path.resolve(root, "." + pathname);
  if (!file.startsWith(root + path.sep) && file !== root) { res.writeHead(403).end(); return; }
  let stat;
  try { stat = fs.statSync(file); } catch { /* SPA routes fall back below. */ }
  if (!stat?.isFile()) {
    if (path.extname(pathname) && pathname !== "/index.html") { res.writeHead(404).end(); return; }
    file = path.join(root, "index.html"); stat = fs.statSync(file);
  }
  const headers = { "Content-Type": types[path.extname(file)] || "application/octet-stream", "Accept-Ranges": "bytes",
    "Cache-Control": file.endsWith("index.html") ? "no-store" : "public, max-age=3600", "X-Content-Type-Options": "nosniff" };
  let start = 0, end = stat.size - 1, status = 200;
  if (req.headers.range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
    if (!match || (!match[1] && !match[2])) { res.writeHead(416, { "Content-Range": `bytes */${stat.size}` }).end(); return; }
    if (match[1]) { start = Number(match[1]); end = match[2] ? Math.min(end, Number(match[2])) : end; }
    else start = match[2] !== "0" ? Math.max(0, stat.size - Number(match[2])) : stat.size;
    if (start > end || start >= stat.size) { res.writeHead(416, { "Content-Range": `bytes */${stat.size}` }).end(); return; }
    status = 206; headers["Content-Range"] = `bytes ${start}-${end}/${stat.size}`;
  }
  headers["Content-Length"] = String(Math.max(0, end - start + 1));
  res.writeHead(status, headers);
  if (req.method === "HEAD") { res.end(); return; }
  fs.createReadStream(file, { start, end }).on("error", () => res.destroy()).pipe(res);
});
server.listen(port, host, () => console.log(`Da RoastBox on ${host}:${port}; /api -> ${upstream.origin}`));
process.on("SIGTERM", () => server.close(() => process.exit(0)));
