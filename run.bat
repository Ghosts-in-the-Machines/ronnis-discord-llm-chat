@echo off
setlocal
cd /d "%~dp0"

if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate

python -m pip install -q -r requirements.txt

if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [SYSTEM] Created .env from .env.example. Fill in DISCORD_BOT_TOKEN before production use.
    )
)

if not exist data mkdir data

echo [SYSTEM] Starting Discord handler...
start "discord-handler" cmd /k "call venv\Scripts\activate && python src\discord\handler.py"

echo [SYSTEM] Starting Discord worker...
start "discord-worker" cmd /k "call venv\Scripts\activate && python src\worker.py"

pause
