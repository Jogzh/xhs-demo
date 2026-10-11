@echo off
rem Daily metrics entry (scheduled task xhs-agent-daily-metrics).
rem Collects interaction data -> score -> close T+7 -> refresh insights.
rem Log: data\sched_metrics.log (UTF-8 from python)
cd /d D:\Desktop\py_proj\xhs-demo
set PYTHONPATH=src
echo ===== %date% %time% ===== >> data\sched_metrics.log
D:\myenvs\miniconda\python.exe -m xhs_agent metrics --auto >> data\sched_metrics.log 2>&1
D:\myenvs\miniconda\python.exe -m xhs_agent refresh >> data\sched_metrics.log 2>&1
