#!/bin/bash
cd /home/somil/frappe/frappe-bench-v15
export PATH=$PATH:~/.local/bin
~/.local/bin/bench --site dev15.local execute apps.report_center.fetch_report.execute
