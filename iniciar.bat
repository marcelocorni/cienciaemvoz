@echo off
cd /d "%~dp0"
where uv >nul 2>nul
if %errorlevel% equ 0 (
  uv run --python 3.12 --with-requirements requirements-lock.txt streamlit run app.py
) else (
  if not exist .venv\Scripts\python.exe py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
  .venv\Scripts\python.exe -m streamlit run app.py
)
pause
