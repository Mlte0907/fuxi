#!/usr/bin/env python3
"""轻量 HTTP 代理：将 GitHub CONNECT 请求重定向到 gh-proxy.com 镜像。

无需 MITM，仅拦截 CONNECT 隧道阶段改道。纯 stdlib，零依赖。
启动：python3 gh_tunnel_proxy.py [port]  （默认 8080）
"""
import contextlib
import logging
import select
import socket
import sys
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gh-proxy")

GITHUB_HOSTS = {
    "github.com", "api.github.com", "raw.githubusercontent.com",
    "objects.githubusercontent.com", "github.githubassets.com",
}
PROXY_HOST = "gh-proxy.com"
BUFSIZE = 65536


def relay(a: socket.socket, b: socket.socket):
    """双向字节搬运"""
    sockets = [a, b]
    while True:
        try:
            r, _, _ = select.select(sockets, [], [], 30)
        except (OSError, ValueError):
            break
        if not r:
            break
        for src in r:
            dst = b if src is a else a
            try:
                data = src.recv(BUFSIZE)
            except OSError:
                return
            if not data:
                return
            try:
                dst.sendall(data)
            except OSError:
                return


def http_tunnel(client: socket.socket, host: str, port: int):
    """普通 HTTP CONNECT 隧道"""
    try:
        remote = socket.create_connection((host, port), timeout=10)
    except OSError as e:
        logger.warning(f"CONNECT failed: {host}:{port} — {e}")
        with contextlib.suppress(OSError):
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        return
    try:
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    except OSError:
        remote.close()
        return
    t1 = threading.Thread(target=relay, args=(client, remote), daemon=True)
    t2 = threading.Thread(target=relay, args=(remote, client), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def handle_client(client: socket.socket):
    """处理一个客户端连接"""
    try:
        client.settimeout(30)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = client.recv(BUFSIZE)
            if not chunk:
                return
            data += chunk
            if len(data) > 65536:
                return

        req_line = data.split(b"\r\n")[0].decode("utf-8", errors="replace")
        parts = req_line.split()
        if len(parts) < 2:
            return

        method = parts[0]
        target = parts[1]

        if method == "CONNECT":
            # target = host:port
            host, _, port_str = target.partition(":")
            port = int(port_str) if port_str else 443

            if host in GITHUB_HOSTS:
                logger.info(f"[GH→Proxy] CONNECT {host}:{port} → {PROXY_HOST}")
                http_tunnel(client, PROXY_HOST, port)
            else:
                http_tunnel(client, host, port)
        else:
            # 普通 HTTP 请求 — 直接转发
            try:
                from urllib.parse import urlparse
                parsed = urlparse(target)
                dst_host = parsed.hostname
                dst_port = parsed.port or 80
                if dst_host in GITHUB_HOSTS:
                    new_target = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
                    if not new_target:
                        new_target = "/"
                    # 整个原始 URL 作为 gh-proxy 的路径
                    gh_url = f"http://{PROXY_HOST}/{target}"
                    logger.info(f"[GH→Proxy] HTTP GET {target} → {gh_url}")
                    remote = socket.create_connection((PROXY_HOST, 80), timeout=10)
                    # 重写请求行
                    new_req = data.replace(target.encode(), gh_url.encode(), 1)
                    remote.sendall(new_req)
                else:
                    remote = socket.create_connection((dst_host, dst_port), timeout=10)
                    remote.sendall(data)
                # Relay response back
                t1 = threading.Thread(target=relay, args=(client, remote), daemon=True)
                t2 = threading.Thread(target=relay, args=(remote, client), daemon=True)
                t1.start()
                t2.start()
                t1.join(timeout=60)
            except OSError as e:
                logger.warning(f"HTTP request failed: {target} — {e}")
    except Exception as e:
        logger.debug(f"Client handler error: {e}")
    finally:
        with contextlib.suppress(OSError):
            client.close()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(128)
    logger.info(f"GitHub tunnel proxy listening on 127.0.0.1:{port}")
    logger.info(f"Redirecting GitHub hosts to {PROXY_HOST}: {GITHUB_HOSTS}")
    try:
        while True:
            client, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client,), daemon=True)
            t.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        logger.info("Proxy stopped")


if __name__ == "__main__":
    main()
