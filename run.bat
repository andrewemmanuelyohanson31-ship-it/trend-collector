@echo off
rem Daily job for Task Scheduler: collect trends and append output to logs\collect.log
cd /d "%~dp0"
if not exist logs mkdir logs
echo ==== %date% %time% >> logs\collect.log
rem Ollama normally starts at logon; start it ourselves when the task runs before anyone logs in
curl -s -o nul http://localhost:11434 || (
  set "OLLAMA_MODELS=D:\apps\ollama\models"
  start "" /b D:\apps\ollama\ollama.exe serve
  ping -n 8 127.0.0.1 > nul
)
.venv\Scripts\python.exe collect.py >> logs\collect.log 2>&1
.venv\Scripts\python.exe predict.py >> logs\collect.log 2>&1
