#!/usr/bin/env bash
# Wait for the GitHub deploy run (deploy + smoke test) for a pushed commit and report the result.
# Usage: ./scripts/watch-deploy.sh [sha]      (default: HEAD)
# Exit 0 = deployed and smoke test passed; 1 = run failed (failed-step log printed);
# 2 = commit isn't on origin/Setup; 3 = no run appeared; 4 = run still going after 25 minutes.
# Runs can take several minutes: call it with a 10-minute timeout or in the background.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
BRANCH="${DEPLOY_BRANCH:-Setup}"
sha="$(git rev-parse "${1:-HEAD}")"
short="${sha:0:7}"

git fetch -q origin "$BRANCH" 2>/dev/null
if ! git merge-base --is-ancestor "$sha" "origin/$BRANCH" 2>/dev/null; then
  echo "Commit $short isn't on origin/$BRANCH; only pushes to $BRANCH deploy. Push it first: git push origin HEAD:$BRANCH" >&2
  exit 2
fi

# A run is created for the newest pushed commit; if $sha was pushed together with later
# commits, watch the run for the branch tip instead.
tip="$(git rev-parse "origin/$BRANCH")"
id=""
for _ in $(seq 1 40); do
  for c in "$sha" "$tip"; do
    id="$(gh run list --workflow deploy.yml --branch "$BRANCH" --commit "$c" --limit 1 \
          --json databaseId -q '.[0].databaseId' 2>/dev/null)"
    [ -n "$id" ] && break 2
  done
  sleep 3
done
[ -n "$id" ] || { echo "No deploy run found for $short after 2 minutes. Is .github/workflows/deploy.yml on $BRANCH?" >&2; exit 3; }

url="$(gh run view "$id" --json url -q .url)"
echo "Watching deploy run $id ($url)"
for _ in $(seq 1 150); do
  read -r status conclusion < <(gh run view "$id" --json status,conclusion -q '"\(.status) \(.conclusion)"' 2>/dev/null)
  [ "$status" = "completed" ] && break
  sleep 10
done

if [ "${status:-}" != "completed" ]; then
  echo "Run $id still $status after 25 minutes: $url" >&2
  exit 4
fi
if [ "$conclusion" = "success" ]; then
  echo "Deploy and smoke test passed for $short."
  exit 0
fi
echo "Deploy run $id finished: $conclusion. Failed steps (last 120 lines):"
gh run view "$id" --log-failed 2>/dev/null | tail -120
exit 1
