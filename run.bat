@echo off
rem Daily job for Task Scheduler: collect trends and append output to logs\collect.log
cd /d "%~dp0"
if not exist logs mkdir logs
echo ==== %date% %time% >> logs\collect.log
.venv\Scripts\python.exe collect.py >> logs\collect.log 2>&1
.venv\Scripts\python.exe predict.py >> logs\collect.log 2>&1
