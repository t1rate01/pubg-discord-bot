import os
import shutil
from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.auth import admin_exists, create_admin
from app.core.logging import setup_logging
from app.core.settings_service import initialize_runtime_config, system_state
from app.db.sqlite import init_db
from app.db.models import (
    dashboard_counts,
    list_recent_reports,
    list_tracked_users,
    get_tracked_user_by_id,
    create_tracked_user,
    update_tracked_user,
    delete_tracked_user,
    save_runtime_config,
    get_report_by_id,
    list_report_matches,
    get_service_control_state,
    set_service_enabled,
    request_service_restart,
    request_all_services_restart,
)
from app.db.runtime_models import (
    list_recent_jobs,
    get_job_counts,
)
from app.web.deps import require_basic_auth

setup_logging()
init_db()

app = FastAPI(title="PUBG Discord Bot Admin")

BASE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads" / "join_sounds"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def save_join_sound_file(discord_user_id: str, upload: UploadFile | None) -> str | None:
    if not upload or not upload.filename:
        return None

    filename = upload.filename.lower()
    if not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only .mp3 files are allowed for join sounds")

    safe_name = f"{discord_user_id}.mp3"
    target_path = UPLOADS_DIR / safe_name

    with target_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    return str(target_path)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    state = system_state()

    if not admin_exists():
        return redirect("/setup/admin")

    if not state["runtime_config_complete"]:
        return redirect("/setup/runtime")

    require_basic_auth(request)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "state": state,
            "counts": dashboard_counts(),
            "recent_reports": list_recent_reports(),
        },
    )


@app.get("/setup/admin", response_class=HTMLResponse)
async def setup_admin_page(request: Request):
    if admin_exists():
        return redirect("/")
    return templates.TemplateResponse("setup.html", {"request": request, "step": "admin"})


@app.post("/setup/admin")
async def setup_admin_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    owner_discord_id: str = Form(""),
):
    if admin_exists():
        return redirect("/")

    if password != confirm_password:
        return templates.TemplateResponse(
            "setup.html",
            {
                "request": request,
                "step": "admin",
                "error": "Passwords do not match.",
            },
        )

    create_admin(username.strip(), password)
    if owner_discord_id.strip():
        save_runtime_config({"admin_discord_ids": [owner_discord_id.strip()]})

    return redirect("/setup/runtime")


@app.get("/setup/runtime", response_class=HTMLResponse)
async def setup_runtime_page(request: Request):
    if not admin_exists():
        return redirect("/setup/admin")

    state = system_state()
    if state["runtime_config_complete"]:
        return redirect("/")

    require_basic_auth(request)
    return templates.TemplateResponse("setup.html", {"request": request, "step": "runtime"})


@app.post("/setup/runtime")
async def setup_runtime_action(
    request: Request,
    discord_bot_token: str = Form(...),
    pubg_api_key: str = Form(...),
    discord_guild_id: str = Form(...),
    discord_target_voice_channel_id: str = Form(...),
    discord_target_text_channel_id: str = Form(...),
    tracked_team_name: str = Form("My Stack"),
    admin_discord_ids_csv: str = Form(""),
):
    require_basic_auth(request)

    admin_ids = [x.strip() for x in admin_discord_ids_csv.split(",") if x.strip()]

    initialize_runtime_config(
        discord_bot_token=discord_bot_token,
        pubg_api_key=pubg_api_key,
        discord_guild_id=discord_guild_id,
        discord_target_voice_channel_id=discord_target_voice_channel_id,
        discord_target_text_channel_id=discord_target_text_channel_id,
        tracked_team_name=tracked_team_name,
        admin_discord_ids=admin_ids,
    )

    return redirect("/")


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    require_basic_auth(request)
    return templates.TemplateResponse(
        "users.html",
        {"request": request, "users": list_tracked_users()},
    )


@app.get("/users/new", response_class=HTMLResponse)
async def new_user_page(request: Request):
    require_basic_auth(request)
    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": None, "mode": "create"},
    )


@app.post("/users/new")
async def create_user_action(
    request: Request,
    discord_user_id: str = Form(...),
    discord_name: str = Form(...),
    pubg_handle: str = Form(""),
    tracking_enabled: str | None = Form(None),
    history_enabled: str | None = Form(None),
    join_sound_enabled: str | None = Form(None),
    join_sound_file: UploadFile | None = File(None),
):
    require_basic_auth(request)

    join_sound_path = save_join_sound_file(discord_user_id.strip(), join_sound_file)

    create_tracked_user(
        discord_user_id=discord_user_id.strip(),
        discord_name=discord_name.strip(),
        pubg_handle=pubg_handle.strip() or None,
        tracking_enabled=tracking_enabled is not None,
        history_enabled=history_enabled is not None,
        join_sound_enabled=join_sound_enabled is not None,
        join_sound_path=join_sound_path,
    )
    return redirect("/users")


@app.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_page(request: Request, user_id: int):
    require_basic_auth(request)

    user = get_tracked_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": user, "mode": "edit"},
    )


@app.post("/users/{user_id}/edit")
async def edit_user_action(
    request: Request,
    user_id: int,
    discord_user_id: str = Form(...),
    discord_name: str = Form(...),
    pubg_handle: str = Form(""),
    tracking_enabled: str | None = Form(None),
    history_enabled: str | None = Form(None),
    join_sound_enabled: str | None = Form(None),
    join_sound_file: UploadFile | None = File(None),
):
    require_basic_auth(request)

    user = get_tracked_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    uploaded_path = save_join_sound_file(discord_user_id.strip(), join_sound_file)
    final_sound_path = uploaded_path if uploaded_path else user["join_sound_path"]

    update_tracked_user(
        user_id=user_id,
        discord_user_id=discord_user_id.strip(),
        discord_name=discord_name.strip(),
        pubg_handle=pubg_handle.strip() or None,
        tracking_enabled=tracking_enabled is not None,
        history_enabled=history_enabled is not None,
        join_sound_enabled=join_sound_enabled is not None,
        join_sound_path=final_sound_path,
    )
    return redirect("/users")


@app.post("/users/{user_id}/delete")
async def delete_user_action(request: Request, user_id: int):
    require_basic_auth(request)
    delete_tracked_user(user_id)
    return redirect("/users")


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    require_basic_auth(request)
    return templates.TemplateResponse(
        "reports.html",
        {"request": request, "reports": list_recent_reports(100)},
    )


@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail_page(request: Request, report_id: int):
    require_basic_auth(request)

    report = get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    matches = list_report_matches(report_id)

    return templates.TemplateResponse(
        "report_detail.html",
        {"request": request, "report": report, "matches": matches},
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    require_basic_auth(request)
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "state": system_state()},
    )


@app.post("/settings")
async def settings_action(
    request: Request,
    tracked_team_name: str = Form(...),
    admin_discord_ids_csv: str = Form(""),
    voice_join_sounds_enabled: str | None = Form(None),
    pubg_job_worker_idle_poll_seconds: str = Form(...),
    pubg_job_result_poll_seconds: str = Form(...),
    pubg_job_result_max_wait_seconds: str = Form(...),
    pubg_rate_limit_max_requests: str = Form(...),
    pubg_rate_limit_window_seconds: str = Form(...),
):
    require_basic_auth(request)

    admin_ids = [x.strip() for x in admin_discord_ids_csv.split(",") if x.strip()]

    save_runtime_config(
        {
            "tracked_team_name": tracked_team_name.strip() or "My Stack",
            "admin_discord_ids": admin_ids,
            "voice_join_sounds_enabled": voice_join_sounds_enabled is not None,
            "pubg_job_worker_idle_poll_seconds": pubg_job_worker_idle_poll_seconds.strip(),
            "pubg_job_result_poll_seconds": pubg_job_result_poll_seconds.strip(),
            "pubg_job_result_max_wait_seconds": pubg_job_result_max_wait_seconds.strip(),
            "pubg_rate_limit_max_requests": pubg_rate_limit_max_requests.strip(),
            "pubg_rate_limit_window_seconds": pubg_rate_limit_window_seconds.strip(),
        }
    )

    return redirect("/settings")


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    require_basic_auth(request)

    log_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "app.log")
    lines = []
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-300:]

    return templates.TemplateResponse(
        "logs.html",
        {"request": request, "lines": lines},
    )


@app.get("/system", response_class=HTMLResponse)
async def system_page(request: Request):
    require_basic_auth(request)

    state = system_state()
    jobs = list_recent_jobs(100)
    job_counts = get_job_counts()
    service_control = get_service_control_state()

    return templates.TemplateResponse(
        "system.html",
        {
            "request": request,
            "state": state,
            "jobs": jobs,
            "job_counts": job_counts,
            "service_control": service_control,
        },
    )


@app.post("/system/service/{service_name}/toggle")
async def toggle_service(request: Request, service_name: str):
    require_basic_auth(request)

    if service_name not in {"bot", "worker"}:
        raise HTTPException(status_code=400, detail="Invalid service name")

    service_control = get_service_control_state()
    currently_enabled = service_control[f"{service_name}_enabled"]
    set_service_enabled(service_name, not currently_enabled)

    return redirect("/system")


@app.post("/system/service/{service_name}/restart")
async def restart_service(request: Request, service_name: str):
    require_basic_auth(request)

    if service_name not in {"bot", "worker"}:
        raise HTTPException(status_code=400, detail="Invalid service name")

    request_service_restart(service_name)
    return redirect("/system")


@app.post("/system/restart-all")
async def restart_all_services(request: Request):
    require_basic_auth(request)
    request_all_services_restart()
    return redirect("/system")