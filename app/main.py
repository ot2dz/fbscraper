# -*- coding: utf-8 -*-
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.auth import COOKIE_NAME, is_logged_in, make_session, verify_password
from app.config import ADMIN_PASSWORD, ensure_dirs
from app.jobs import current_job, enqueue, queue_status, start_worker
from app.scraper_runner import normalize_target
from app.telegram_bot import bot

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    db.init_db()
    start_worker()
    await bot.start()
    yield
    await bot.stop()


app = FastAPI(title="FB Scraper Bot", lifespan=lifespan)


def _auth_redirect(request: Request):
    if is_logged_in(request):
        return None
    return RedirectResponse("/login", status_code=303)


def _ctx(request, **extra):
    data = {
        "request": request,
        "bot": bot.status(),
        "queue": queue_status(),
        "default_admin_password": ADMIN_PASSWORD == "admin",
        "current": current_job(),
    }
    data.update(extra)
    return data


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "bot": bot.status()["running"]}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_logged_in(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login(request: Request, password: str = Form("")):
    if not verify_password(password):
        return templates.TemplateResponse(request, "login.html", {"error": "كلمة المرور غير صحيحة"}, status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, make_session(), httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = _auth_redirect(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(request, settings=db.all_settings(), jobs=db.list_jobs(limit=15)),
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: int = 0):
    redirect = _auth_redirect(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "settings.html", _ctx(request, settings=db.all_settings(), saved=saved))


@app.post("/settings")
async def save_settings(
    request: Request,
    telegram_token: str = Form(""),
    telegram_enabled: str = Form("0"),
    telegram_allow_all: str = Form("0"),
    telegram_allowed_ids: str = Form(""),
    default_posts: str = Form("30"),
    max_posts: str = Form("200"),
    default_days: str = Form("30"),
    proxy: str = Form(""),
    request_timeout: str = Form("30"),
):
    redirect = _auth_redirect(request)
    if redirect:
        return redirect
    values = {
        "telegram_token": telegram_token.strip(),
        "telegram_enabled": "1" if telegram_enabled == "1" else "0",
        "telegram_allow_all": "1" if telegram_allow_all == "1" else "0",
        "telegram_allowed_ids": telegram_allowed_ids.strip(),
        "default_posts": str(max(1, int(default_posts or 30))),
        "max_posts": str(max(1, int(max_posts or 200))),
        "default_days": str(max(1, int(default_days or 30))),
        "proxy": proxy.strip(),
        "request_timeout": str(max(5, int(request_timeout or 30))),
    }
    for key, value in values.items():
        db.set_setting(key, value)
    await bot.start()
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/api/scrape")
async def api_scrape(
    request: Request,
    target: str = Form(...),
    posts: str = Form("30"),
    days: str = Form("30"),
):
    if not is_logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        clean_target = normalize_target(target)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    max_posts = int(db.get_setting("max_posts", "200") or 200)
    job = enqueue(
        clean_target,
        max(1, min(int(posts or 30), max_posts)),
        max(1, int(days or 30)),
        source="web",
    )
    return {"job": job}


@app.post("/api/debug/browser")
async def api_debug_browser(request: Request, target: str = Form(""), url: str = Form("")):
    """Open a page in Chromium and report what Facebook served (no scraping)."""
    if not is_logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if url:
        if not url.startswith("https://"):
            return JSONResponse({"error": "url must start with https://"}, status_code=400)
        page_url = url
    else:
        try:
            clean_target = normalize_target(target)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        page_url = f"https://www.facebook.com/{clean_target}?locale=en_us"

    def work():
        import time as _time

        from app.config import CHROMEDRIVER_PATH
        from fb_graphql_scraper.base.base_page import BasePage

        page = BasePage(driver_path=CHROMEDRIVER_PATH, open_browser=False)
        try:
            page.driver.get(page_url)
            _time.sleep(12)
            requests_seen = [
                f"{req.method} {req.url[:180]}" for req in list(page.driver.requests)[:40]
            ]
            return {
                "url": page.driver.current_url,
                "title": page.driver.title,
                "requests": len(page.driver.requests),
                "request_list": requests_seen,
                "source_length": len(page.driver.page_source),
                "source_head": page.driver.page_source[:1500],
            }
        finally:
            try:
                page.quit_driver()
            except Exception:  # noqa: BLE001
                pass

    from fastapi.concurrency import run_in_threadpool

    return await run_in_threadpool(work)


@app.post("/api/debug/http")
async def api_debug_http(request: Request, url: str = Form(...)):
    """Plain HTTP request (uses the configured proxy) to see what Meta returns."""
    if not is_logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if not url.startswith("https://"):
        return JSONResponse({"error": "url must start with https://"}, status_code=400)

    def work():
        import requests

        kwargs = {"timeout": 30, "allow_redirects": True}
        proxy = db.get_setting("proxy", "")
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        response = requests.get(url, **kwargs)
        return {
            "status": response.status_code,
            "final_url": response.url,
            "length": len(response.content),
            "head": response.text[:1200],
        }

    from fastapi.concurrency import run_in_threadpool

    return await run_in_threadpool(work)


@app.get("/api/jobs/{job_id}")
async def api_job(request: Request, job_id: str):
    if not is_logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    job = db.get_job(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"job": job}


@app.post("/api/bot/restart")
async def api_bot_restart(request: Request):
    if not is_logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    await bot.start()
    return {"bot": bot.status()}


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request):
    redirect = _auth_redirect(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "jobs.html", _ctx(request, jobs=db.list_jobs(limit=100)))


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_page(request: Request, job_id: str):
    redirect = _auth_redirect(request)
    if redirect:
        return redirect
    job = db.get_job(job_id)
    if not job:
        return templates.TemplateResponse(request, "job.html", _ctx(request, job=None, posts=[]), status_code=404)
    posts = []
    if job.get("result_path") and os.path.exists(job["result_path"]):
        try:
            with open(job["result_path"], encoding="utf-8") as handle:
                posts = json.load(handle).get("data", [])
        except Exception:  # noqa: BLE001
            posts = []
    log_tail = ""
    if job.get("log_path") and os.path.exists(job["log_path"]):
        with open(job["log_path"], encoding="utf-8", errors="replace") as handle:
            log_tail = handle.read()[-4000:]
    return templates.TemplateResponse(request, "job.html", _ctx(request, job=job, posts=posts, log_tail=log_tail))


@app.get("/results/{job_id}.json")
async def download_result(request: Request, job_id: str):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)
    job = db.get_job(job_id)
    if not job or not job.get("result_path") or not os.path.exists(job["result_path"]):
        return PlainTextResponse("not found", status_code=404)
    return FileResponse(job["result_path"], media_type="application/json", filename=f"{job_id}.json")
