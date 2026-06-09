"""Standalone jobs run outside the web process (systemd timers / cron).

Each module is runnable as `python -m jobs.<name>` from the backend/
directory (the flat import paths require that working directory, same as
the app itself).
"""
