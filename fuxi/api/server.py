"""伏羲 v1.0 — FastAPI app 工厂"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from fuxi.auth.middleware import AuthMiddleware
from fuxi.config import config
from fuxi.kernel.lifespan import Lifespan
from fuxi.models import ApiResponse
from fuxi.observability.logging import setup_logging
from fuxi.store.migrations import init_db

logger = logging.getLogger("fuxi.api.server")

_lifespan = Lifespan()


def create_app() -> FastAPI:
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动
        logger.info(f"FuXi v1.0 starting on {config.host}:{config.port}")
        init_db()
        _lifespan.start()

        # 启动全部非实验引擎 + cognitive_loop 自主调度器
        from fuxi.engines.base import get_engine_registry
        get_engine_registry().start_all(include_experimental=False)
        loop_engine = get_engine_registry().get("cognitive_loop")
        if loop_engine:
            loop_engine.start()
            # 使用引擎自身 interval（180s）作为调度周期，消除冗余轮询
            _lifespan.spawn_background(
                lambda: loop_engine._execute(),
                name="cognitive-loop",
                interval=loop_engine.interval,
            )
        # 启动 Cron 调度器
        from fuxi.cron.scheduler import get_cron_scheduler
        get_cron_scheduler().start_background(interval=60)
        # 启动异步写队列（用于非关键写入）
        from fuxi.store.write_queue import get_write_queue
        get_write_queue().start()
        # 加载模型路由
        from fuxi.agent.model_router import reload_routes
        reload_routes()
        # 注册内部 ACP 客户端，使协议消息在组件间流通
        from fuxi.acp.client import get_acp_client
        get_acp_client().register()

        # 定时健康扫描（每2小时）
        def _run_health_scan():
            import subprocess, sys, os
            script = os.path.join(os.path.dirname(__file__), "..", "..", "fuxi_scripts", "health_scan.py")
            if os.path.exists(script):
                result = subprocess.run([sys.executable, script, "--alert"], capture_output=True, timeout=60)
                if result.returncode != 0:
                    logger.warning("Health scan found issues:\n%s", result.stdout.decode()[:1000])
                else:
                    logger.debug("Health scan OK")

        _lifespan.spawn_background(
            _run_health_scan,
            name="health-scan",
            interval=7200,
        )
        logger.info("Engine scheduler started (autonomous mode)")

        # 启动 Feishu IM Engine（larkcc 子进程）
        from fuxi.engines.feishu_im import get_feishu_im_engine
        feishu_im = get_feishu_im_engine()
        feishu_im.start()

        yield
        # 关闭
        get_engine_registry().stop_all()
        feishu_im.stop()
        from fuxi.store.write_queue import get_write_queue
        get_write_queue().stop()
        _lifespan.stop()
        logger.info("FuXi v1.0 stopped")

    app = FastAPI(
        title="FuXi v1.1",
        description="FuXi - Unified Memory & Cognitive Engine System",
        version="1.1.0",
        lifespan=lifespan
    )

    # Rate Limiting
    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    # CORS
    _cors_origins = config.cors_origins if hasattr(config, "cors_origins") else ["http://localhost:19528", "http://127.0.0.1:19528", "http://localhost:19527", "http://127.0.0.1:19527"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )

    # Auth
    app.add_middleware(AuthMiddleware)

    # API 版本协商中间件 — 注入版本标头
    @app.middleware("http")
    async def version_middleware(request: Request, call_next):
        from fuxi.api.versioning import (
            CURRENT_VERSION,
            VERSION_HEADER,
            get_deprecation_headers,
            negotiate_version,
        )
        accept_ver = request.headers.get("Accept-Version", "")
        matched = negotiate_version(accept_ver) if accept_ver else CURRENT_VERSION
        response = await call_next(request)
        response.headers[VERSION_HEADER] = matched
        # 弃用标头
        dep_headers = get_deprecation_headers(request.url.path)
        for key, val in dep_headers.items():
            response.headers[key] = val
        return response

    # API Prometheus 指标中间件
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        import time
        start = time.time()
        response = await call_next(request)
        from fuxi.observability.metrics import record_api_request
        record_api_request(
            request.method,
            request.url.path,
            response.status_code,
            time.time() - start,
        )
        return response

    # 全局异常处理器 — 统一错误响应格式
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        from fastapi import HTTPException
        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content=ApiResponse.error(exc.status_code, exc.detail if isinstance(exc.detail, str) else str(exc.detail)).model_dump()
            )
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
        return JSONResponse(
            status_code=500,
            content=ApiResponse.error(500, "Internal server error").model_dump()
        )

    # 注册路由
    from fuxi.api.routes_adaptive import router as adaptive_router
    from fuxi.api.routes_admin import router as admin_router
    from fuxi.api.routes_agents import router as agent_router
    from fuxi.api.routes_bridge import router as bridge_router
    from fuxi.api.routes_collaboration import router as collab_router
    from fuxi.api.routes_cron import router as cron_router
    from fuxi.api.routes_decision import router as decision_router
    from fuxi.api.routes_engines import router as eng_router
    from fuxi.api.routes_graph import router as graph_router
    from fuxi.api.routes_memory import router as mem_router
    from fuxi.api.routes_metrics import router as metrics_router
    from fuxi.api.routes_token import router as token_router
    from fuxi.api.routes_anthropic_proxy import router as anthropic_proxy_router
    from fuxi.api.routes_model import router as model_router
    from fuxi.api.routes_persona import router as persona_router
    from fuxi.api.routes_profile import router as profile_router
    from fuxi.api.routes_system import router as sys_router
    from fuxi.api.routes_tasks import router as task_router
    from fuxi.api.routes_tools import router as tool_router
    from fuxi.compat.compat_router import router as compat_router
    from fuxi.acp.server import router as acp_router
    from fuxi.api.routes_skills import router as skills_router
    from fuxi.api.routes_versions import router as versions_router
    from fuxi.api.ws import router as ws_router

    app.include_router(mem_router, prefix="/api/v2")
    app.include_router(eng_router, prefix="/api/v2")
    app.include_router(agent_router, prefix="/api/v2")
    app.include_router(bridge_router, prefix="/api/v2")
    app.include_router(collab_router, prefix="/api/v2")
    app.include_router(admin_router, prefix="/api/v2")
    app.include_router(sys_router, prefix="/api/v2")
    app.include_router(ws_router, prefix="/api/v2")
    app.include_router(graph_router, prefix="/api/v2")
    app.include_router(task_router, prefix="/api/v2")
    app.include_router(tool_router, prefix="/api/v2")
    app.include_router(compat_router, prefix="/api/v2")
    app.include_router(acp_router)
    app.include_router(cron_router, prefix="/api/v2")
    app.include_router(model_router, prefix="/api/v2")
    app.include_router(anthropic_proxy_router, prefix="/anthropic")
    app.include_router(profile_router, prefix="/api/v2")
    app.include_router(metrics_router)    # /metrics at root
    app.include_router(token_router, prefix="/api/v2")
    app.include_router(versions_router)   # /api/versions at root
    app.include_router(adaptive_router, prefix="/api/v2")
    app.include_router(decision_router, prefix="/api/v2")
    app.include_router(persona_router, prefix="/api/v2")
    app.include_router(skills_router, prefix="/api/v2")

    # 短路径别名（兼容简写 URL）
    @app.get("/api/v2/system", include_in_schema=False)
    async def system_alias():
        return RedirectResponse(url="/api/v2/system/info")

    @app.get("/api/v2/graph", include_in_schema=False)
    async def graph_alias():
        return RedirectResponse(url="/api/v2/graph/edges")

    @app.get("/api/v2/cron", include_in_schema=False)
    async def cron_alias():
        return RedirectResponse(url="/api/v2/cron/tasks")

    @app.get("/api/v2/models", include_in_schema=False)
    async def models_alias():
        return RedirectResponse(url="/api/v2/models/routes")

    # Dashboard
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        @app.get("/dashboard", include_in_schema=False)
        async def dashboard():
            content = (static_dir / "index.html").read_text()
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content)

        @app.get("/", include_in_schema=False)
        async def root():
            return RedirectResponse(url="/dashboard")

    # 健康检查
    @app.get("/health")
    async def health():
        from fuxi.observability.health import quick_health_check
        return ApiResponse.ok(quick_health_check())

    @app.get("/health/deep")
    async def deep_health():
        from fuxi.observability.health import deep_health_check
        return ApiResponse.ok(deep_health_check())

    logger.info("FuXi v1.0 app created with all routes")
    return app
