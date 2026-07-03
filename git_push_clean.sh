#!/bin/bash
set -e

echo "=== Configuring Git ==="
git config --global user.name "somilvaishya"
git config --global user.email "somilsearchosis@gmail.com"

echo "=== Adding files ==="
git add .

echo "=== Committing ==="
git commit -m "feat: implement General Ledger Audit report" || true

echo "=== Renaming branch ==="
git branch -M main || true

echo "=== Adding remote ==="
git remote add origin https://github.com/Somilvaishya/report_center.git || git remote set-url origin https://github.com/Somilvaishya/report_center.git

echo "=== Pushing to GitHub ==="
git push -u origin main
