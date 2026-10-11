@echo off
rem Daily publish entry (scheduled task xhs-agent-daily-publish).
rem Only publishes queued AI content data\pending_note.json; skips if none.
rem Log: data\sched_publish.log (UTF-8 from python)
cd /d D:\Desktop\py_proj\xhs-demo
set PYTHONPATH=src
echo ===== %date% %time% ===== >> data\sched_publish.log
D:\myenvs\miniconda\python.exe -m xhs_agent daily >> data\sched_publish.log 2>&1
