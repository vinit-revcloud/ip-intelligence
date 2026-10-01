"""Location accuracy per vendor, measured against customers' own postal addresses.

Truth: ipintel_curated.qualified_lead_ips rows with a full address (state, city, 5-digit zip). For every
such address, each location vendor's answer in ip_geo, and the pipeline's own resolved answer in
ip_resolved (shown as vendor "resolved"), is compared field by field:
  state  lower-cased and trimmed, equal
  city   lower-cased with everything except letters removed, equal (stricter than the voting key, which
         only compares the first word)
  zip    first five characters, equal
A customer's postal address is where they live, not always where their connection is (mobile carriers,
work networks), so no vendor can reach 100%; the numbers compare vendors with each other.

Only aggregates are exported, never an address or a lead: serving/ipintel_curated/geo_accuracy.json,
read by the API's GET /accuracy/geo.
"""
import common as c

KEY = "%s/serving/ipintel_curated/geo_accuracy.json" % c.PREFIX
MIN_STATE_SAMPLE = 20       # below this a state's percentages are shown but flagged as a small sample


def _sql():
    city = "regexp_replace(lower(trim({x})), '[^a-z]', '')"
    return f"""
WITH lead AS (
  SELECT ip_address, max(lead_state) AS st, max(lead_city) AS ct, max(lead_zip) AS zp
  FROM {c.DB}.qualified_lead_ips WHERE has_full_address GROUP BY ip_address),
ans AS (
  SELECT g.vendor, g.ip_address, g.state, g.city, g.zip_code FROM {c.DB}.ip_geo g JOIN lead l ON l.ip_address = g.ip_address
  UNION ALL
  SELECT 'resolved', r.ip_address, r.state, r.city, r.zip_code FROM {c.DB}.ip_resolved r JOIN lead l ON l.ip_address = r.ip_address),
vendors AS (SELECT count(DISTINCT vendor) AS n FROM ans WHERE vendor <> 'resolved'),
common AS (
  SELECT ip_address FROM ans WHERE vendor <> 'resolved' AND state IS NOT NULL
  GROUP BY ip_address HAVING count(DISTINCT vendor) = (SELECT n FROM vendors)),
m AS (
  SELECT a.vendor, l.st AS lead_state, (cm.ip_address IS NOT NULL) AS in_common,
    (a.state IS NOT NULL OR a.city IS NOT NULL OR a.zip_code IS NOT NULL) AS answered,
    CASE WHEN nullif(trim(a.state), '') IS NOT NULL THEN lower(trim(a.state)) = lower(trim(l.st)) END AS sm,
    CASE WHEN nullif(trim(a.city), '') IS NOT NULL THEN {city.format(x="a.city")} = {city.format(x="l.ct")} END AS cm,
    CASE WHEN nullif(trim(a.zip_code), '') IS NOT NULL THEN substr(trim(a.zip_code), 1, 5) = l.zp END AS zm
  FROM ans a JOIN lead l ON l.ip_address = a.ip_address
  LEFT JOIN common cm ON cm.ip_address = a.ip_address)
SELECT vendor, lead_state, in_common, count(*) AS tested, count_if(answered) AS answered,
  count_if(sm IS NOT NULL) AS state_judged, count_if(sm) AS state_match,
  count_if(cm IS NOT NULL) AS city_judged, count_if(cm) AS city_match,
  count_if(zm IS NOT NULL) AS zip_judged, count_if(zm) AS zip_match,
  count_if(sm IS NOT NULL AND cm IS NOT NULL) AS state_city_judged, count_if(sm AND cm) AS state_city_match
FROM m GROUP BY vendor, lead_state, in_common"""


FIELDS = ["tested", "answered", "state_judged", "state_match", "city_judged", "city_match", "zip_judged",
          "zip_match", "state_city_judged", "state_city_match"]


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def _shape(sums):
    out = {k: sums[k] for k in FIELDS}
    out.update(answered_pct=_pct(sums["answered"], sums["tested"]),
               state_pct=_pct(sums["state_match"], sums["state_judged"]),
               city_pct=_pct(sums["city_match"], sums["city_judged"]),
               zip_pct=_pct(sums["zip_match"], sums["zip_judged"]),
               state_city_pct=_pct(sums["state_city_match"], sums["state_city_judged"]))
    return out


def _add(acc, key, r):
    s = acc.setdefault(key, {k: 0 for k in FIELDS})
    for k in FIELDS:
        s[k] += int(r[k] or 0)


def build():
    data = c.rows(_sql(), timeout_s=300)
    overall, common, by_state = {}, {}, {}
    for r in data:
        _add(overall, r["vendor"], r)
        if r["in_common"]:
            _add(common, r["vendor"], r)
        _add(by_state, (r["vendor"], r["lead_state"]), r)
    order = sorted(overall, key=lambda v: (v == "resolved", -(_shape(overall[v])["state_city_pct"] or 0)))
    truth = max((overall[v]["tested"] for v in overall if v == "resolved"), default=0)
    return {
        "as_of": c.now_iso(),
        "truth": {"source": "qualified_lead_ips (customer postal address)", "addresses": truth,
                  "note": "A postal address is where a customer lives, not always where their connection is, "
                          "so these percentages compare vendors with each other rather than promise a location."},
        "rules": {"state": "same state name", "city": "same city name (letters only, case ignored)",
                  "zip": "same first five digits", "state_city": "state and city both match"},
        "min_state_sample": MIN_STATE_SAMPLE,
        "vendors": [dict(vendor=v, pool="all", **_shape(overall[v])) for v in order],
        "common_pool": {
            "description": "Only the addresses every location vendor answered, so every vendor is judged on the same addresses.",
            "addresses": max((common[v]["tested"] for v in common), default=0),
            "vendors": [dict(vendor=v, pool="common", **_shape(common[v])) for v in order if v in common]},
        "by_state": sorted([dict(vendor=v, state=st, small_sample=by_state[(v, st)]["tested"] < MIN_STATE_SAMPLE,
                                 **_shape(by_state[(v, st)])) for (v, st) in by_state],
                           key=lambda x: (x["state"] or "", x["vendor"])),
    }


def export():
    """Rebuild and save the file. Returns a check for the run log."""
    try:
        doc = build()
        c.s3_put_json(KEY, doc)
        return {"name": "Location accuracy per vendor exported", "passed": True,
                "detail": "%d truth addresses, %d vendors" % (doc["truth"]["addresses"], len(doc["vendors"]))}
    except Exception as e:
        return {"name": "Location accuracy per vendor exported", "passed": False,
                "detail": ("%s: %s" % (type(e).__name__, e))[:300]}
