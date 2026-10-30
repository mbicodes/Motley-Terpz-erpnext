#!/usr/bin/env bash
# Usage: ./deploy.sh <site> [bench_dir]
# Run on the target server as the bench user. Takes a backup, fast-forwards the app, migrates,
# clears cache, restarts and runs the Wash Plan checks.
set -euo pipefail
SITE="${1:?usage: deploy.sh <site> [bench_dir]}"
BENCH="${2:-$HOME/frappe-bench}"
APP="$BENCH/apps/cannabis_management"

cd "$APP"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Uncommitted changes in $APP, stopping:"; git status --short --untracked-files=no; exit 1
fi
cd "$BENCH"
bench --site "$SITE" backup
cd "$APP"
git fetch origin
git merge --ff-only origin/main
cd "$BENCH"
bench --site "$SITE" migrate
bench --site "$SITE" clear-cache
bench build --app cannabis_management
bench restart || sudo supervisorctl restart all || true
bench --site "$SITE" execute cannabis_management.wash_plan_install.verify
echo "Next: add any freezers reported as TODO in Wash Plan Settings, then open /app/wash-plan-board"
