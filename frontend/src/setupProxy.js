// Keep browser API calls same-origin; the proxy, not the browser, contacts FastAPI.
// REACT_APP_BACKEND_URL may still be set for a separately hosted backend.
const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function setupProxy(app) {
  app.use(
    "/api",
    createProxyMiddleware({
      target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8001",
      changeOrigin: true,
    }),
  );
};
