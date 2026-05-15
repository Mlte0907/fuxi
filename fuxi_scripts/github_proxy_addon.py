"""mitmproxy addon: 将 GitHub 请求重定向到 gh-proxy.com 镜像

两步拦截：
1. server_connect — 将上游连接目标从 github.com 改为 gh-proxy.com（绕过 GFW）
2. request — 将请求 URL 改写为 gh-proxy.com 的路径格式
"""
import logging

from mitmproxy import connection, ctx, http

logger = logging.getLogger("github-proxy-addon")

PROXY_HOST = "gh-proxy.com"
GITHUB_HOSTS = {"github.com", "api.github.com", "raw.githubusercontent.com",
                "objects.githubusercontent.com", "github.githubassets.com"}


class GitHubProxy:
    def server_connect(self, data: connection.ServerConnectionHookData) -> None:
        """在连接上游之前，将 GitHub 目标地址改为 gh-proxy.com"""
        server = data.server
        if server.address and server.address[0] in GITHUB_HOSTS:
            original_host = server.address[0]
            port = server.address[1]
            ctx.log.info(f"[GH→Proxy] Rerouting upstream: {original_host}:{port} → {PROXY_HOST}:{port}")
            server.address = (PROXY_HOST, port)
            # 确保 SNI 也指向 gh-proxy.com（否则 TLS 握手失败）
            if hasattr(server, "sni"):
                server.sni = PROXY_HOST

    def request(self, flow: http.HTTPFlow) -> None:
        """将 GitHub 请求的 URL 改写为 gh-proxy.com 路径格式"""
        host = flow.request.pretty_host
        if host in GITHUB_HOSTS:
            original_url = flow.request.pretty_url
            proxy_url = f"https://{PROXY_HOST}/{original_url}"
            ctx.log.info(f"[GH→Proxy] Rewriting URL: {original_url} → {proxy_url}")
            flow.request.url = proxy_url

    def error(self, flow: http.HTTPFlow) -> None:
        if flow.error and "github" in str(flow.error).lower():
            ctx.log.warn(f"[GH→Proxy] Error: {flow.error}")


addons = [GitHubProxy()]
