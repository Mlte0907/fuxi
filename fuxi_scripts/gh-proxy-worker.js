/**
 * Cloudflare Worker — GitHub 代理
 *
 * 部署: npx wrangler deploy
 * 配置: 在 Cloudflare Dashboard 设置自定义域名或直接用 *.workers.dev
 *
 * 支持代理:
 *   - github.com (网页/API)
 *   - api.github.com (REST API)
 *   - raw.githubusercontent.com (原始文件)
 *   - objects.githubusercontent.com (LFS/大文件)
 *   - github.githubassets.com (静态资源)
 */

const GITHUB_HOSTS = [
  "github.com",
  "api.github.com",
  "raw.githubusercontent.com",
  "objects.githubusercontent.com",
  "github.githubassets.com",
];

// 匹配 GitHub 域名的正则
const GH_HOST_PATTERN = /^(?:https?:\/\/)?([^\/]+\.)?(github\.com|githubusercontent\.com|githubassets\.com)/i;

async function handleRequest(request) {
  const url = new URL(request.url);
  const path = url.pathname + url.search;

  // 从路径中提取目标 URL
  // 格式: /https://github.com/user/repo/...
  let targetUrl = path.slice(1); // 去掉开头的 /

  if (!targetUrl || targetUrl === "/") {
    return new Response(
      "GitHub Proxy — 用法: https://<worker>/{github-url}\n\n" +
      "示例: https://<worker>/https://api.github.com/repos/torvalds/linux\n" +
      "      https://<worker>/https://raw.githubusercontent.com/torvalds/linux/master/README.md",
      { status: 200, headers: { "Content-Type": "text/plain; charset=utf-8" } }
    );
  }

  // 兼容没有 https:// 前缀的 URL
  if (!targetUrl.startsWith("http://") && !targetUrl.startsWith("https://")) {
    // 检查是否是 github 域名
    if (targetUrl.match(/^(?:[^\/]+\.)?github/)) {
      targetUrl = "https://" + targetUrl;
    } else {
      return new Response("Invalid URL. Must start with https://github.com/...", { status: 400 });
    }
  }

  // 验证目标 URL 是 GitHub 域名
  let targetHost;
  try {
    targetHost = new URL(targetUrl).hostname;
  } catch {
    return new Response("Invalid URL format", { status: 400 });
  }

  const isGithub = GITHUB_HOSTS.some(gh => targetHost === gh || targetHost.endsWith("." + gh));
  if (!isGithub) {
    return new Response("Only GitHub URLs are supported", { status: 403 });
  }

  // 构造转发请求
  const headers = new Headers(request.headers);
  // 清理代理相关头
  headers.delete("cf-connecting-ip");
  headers.delete("cf-ipcountry");
  headers.delete("cf-ray");
  headers.delete("cf-visitor");
  headers.delete("x-forwarded-for");
  headers.delete("x-forwarded-proto");
  headers.delete("x-real-ip");
  headers.set("Host", targetHost);

  const fetchOptions = {
    method: request.method,
    headers: headers,
    redirect: "follow",
  };

  // 对于非 GET/HEAD 请求，转发 body
  if (!["GET", "HEAD"].includes(request.method)) {
    fetchOptions.body = await request.arrayBuffer();
  }

  try {
    const response = await fetch(targetUrl, fetchOptions);

    // 构造响应，添加 CORS 头
    const respHeaders = new Headers(response.headers);
    respHeaders.set("Access-Control-Allow-Origin", "*");
    respHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, PATCH, OPTIONS");
    respHeaders.set("Access-Control-Allow-Headers", "*");
    // 添加标识头
    respHeaders.set("X-Proxy-By", "gh-proxy-worker");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: respHeaders,
    });
  } catch (err) {
    return new Response(`Proxy error: ${err.message}`, { status: 502 });
  }
}

// 处理 OPTIONS 预检请求
function handleOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Max-Age": "86400",
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return handleOptions();
    }
    return handleRequest(request);
  },
};
