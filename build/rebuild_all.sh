#!/bin/bash
# Full rebuild of the unified tables across all 4.96M addresses.
#
# Safe to re-run. Every step drops and recreates, so a half-finished run is
# fixed by running it again rather than by unpicking anything.
#
#   ./rebuild_all.sh          rebuild everything
#   ./rebuild_all.sh 03       resume from step 03
#
# Order matters. ip_pool defines the address universe every later step joins
# against, and intel_src is the single place the proxy logic lives so the base
# table and its analytics twin can never disagree.
#
# The one thing that is NOT idempotent is the loss of live proxycheck rows, so
# step 00 snapshots them first and step 03 folds them back in. Never skip 00.
set -euo pipefail
cd "$(dirname "$0")"

export AWS_PROFILE=${AWS_PROFILE:-source-creation-tool}
export AWS_REGION=${AWS_REGION:-us-west-2}
BUCKET=datalake-landingzone-221490242148-us-west-2
PREFIX=s3://$BUCKET/ip-intelligence
WG=ipintel_etl          # not enforced, so CTAS may carry external_location
FROM=${1:-00}

say () { printf '\n=== %s\n' "$*"; }

athena () {                                     # athena <sql-file-or-text> <mode>
  local qid st
  if [ "${2:-file}" = "text" ]; then
    qid=$(aws athena start-query-execution --query-string "$1" --work-group $WG \
          --query-execution-context "Database=ipintel_curated" \
          --query QueryExecutionId --output text)
  else
    qid=$(aws athena start-query-execution --query-string "file://$1" --work-group $WG \
          --query-execution-context "Database=ipintel_curated" \
          --query QueryExecutionId --output text)
  fi
  while :; do
    st=$(aws athena get-query-execution --query-execution-id "$qid" \
         --query QueryExecution.Status.State --output text)
    case "$st" in
      SUCCEEDED) return 0 ;;
      FAILED|CANCELLED)
        aws athena get-query-execution --query-execution-id "$qid" \
          --query QueryExecution.Status.StateChangeReason --output text >&2
        return 1 ;;
    esac
    sleep 3
  done
}

reset () {                                      # reset <db.table> <s3-subpath>
  athena "DROP TABLE IF EXISTS $1" text
  aws s3 rm "$PREFIX/$2/" --recursive --quiet
}

step () { [ "$FROM" \> "$1" ] && { echo "  (skipping $1)"; return 1; } || return 0; }

# ---------------------------------------------------------------- 00 snapshot
# Rows proxycheck wrote through the live miss path live in pc_live. They are the
# only rows in the pipeline that cannot be recomputed from source, because each
# one cost a paid API call. Copy them somewhere the rebuild will not touch.
if step 00; then
  say "00  snapshot live proxycheck rows"
  aws s3 rm "$PREFIX/curated/pc_live_prev/" --recursive --quiet
  aws s3 cp "$PREFIX/curated/pc_live/" "$PREFIX/curated/pc_live_prev/" --recursive --quiet
  athena "SELECT count(*) FROM ipintel_curated.pc_live" text
  echo "  pc_live backed up to curated/pc_live_prev/"
fi

if step 01; then
  say "01  ip_pool         the address universe, 4.96M rows"
  reset ipintel_curated.ip_pool curated/ip_pool
  athena 01_ip_pool.sql
fi

if step 02; then
  say "02  ip_geo          IP2Location over the whole pool, plus API vendors"
  reset unified.ip_geo unified/ip_geo
  athena 02_ip_geo.sql
fi

if step 03; then
  say "03  intel_src       PX12 + FraudLogix + lists + pc_live"
  reset ipintel_curated.intel_src curated/intel_src
  athena 03_intel_src.sql
fi

if step 04; then
  say "04  ip_intelligence"
  reset unified.ip_intelligence unified/ip_intelligence
  athena 04_ip_intelligence.sql
fi

if step 05; then
  say "05  ip_intelligence_analytics"
  reset unified.ip_intelligence_analytics unified/ip_intelligence_analytics
  athena 05_ip_intelligence_analytics.sql
fi

if step 06; then
  say "06  vendor_overview_proxy"
  reset unified.vendor_overview_proxy unified/vendor_overview_proxy
  athena 06_vendor_overview_proxy.sql
fi

# ------------------------------------------------------------------ 07 verify
# A build that finishes is not a build that is correct. These three are the
# checks that have actually caught bugs here: a silently empty vendor, a range
# join that fanned out, and losing the paid-for rows.
say "07  verify"
cat > /tmp/_verify.sql <<'SQL'
SELECT 'ip_geo rows'                AS check, CAST(count(*) AS varchar) AS value FROM unified.ip_geo
UNION ALL SELECT 'ip_geo duplicate pairs', CAST(count_if(n>1) AS varchar)
  FROM (SELECT ip_address, vendor, count(*) n FROM unified.ip_geo GROUP BY ip_address, vendor)
UNION ALL SELECT 'ip_intelligence rows', CAST(count(*) AS varchar) FROM unified.ip_intelligence
UNION ALL SELECT 'ip_intelligence duplicate pairs', CAST(count_if(n>1) AS varchar)
  FROM (SELECT ip_address, vendor, count(*) n FROM unified.ip_intelligence GROUP BY ip_address, vendor)
UNION ALL SELECT 'vendors with zero rows in ip_geo', CAST(7 - count(DISTINCT vendor) AS varchar) FROM unified.ip_geo
UNION ALL SELECT 'live proxycheck rows kept', CAST(count(*) AS varchar) FROM ipintel_curated.pc_live
SQL
athena /tmp/_verify.sql
echo
echo "Expected: 4,966,911 geo rows / 9,404,725 intelligence rows / 0 duplicates"
echo "          0 missing vendors / pc_live count unchanged from step 00"
echo
echo "Done. Re-export the two overview JSON files if the scorecards changed."
