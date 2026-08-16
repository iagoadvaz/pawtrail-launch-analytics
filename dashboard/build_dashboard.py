"""Render the PawTrail decision board from the exported control CSVs.

WHY THIS IS GENERATED AND NOT HAND-WRITTEN: a hand-edited dashboard drifts from
the warehouse the moment a metric changes, and a binary Tableau workbook cannot
be reviewed in a diff at all. Generating the page means `git diff` shows number
changes, and a stale CSV is a build failure instead of a silently wrong chart.

EVERY NUMBER COMES FROM A CSV. There are no literals from the design mock in this
file -- those were illustrative. If a control file is missing, the build raises
rather than rendering a placeholder: a dashboard showing 'TODO' passes review in
a way an exception never does.
"""
from __future__ import annotations

import csv
import html
from pathlib import Path

REQUIRED_CONTROL_FILES = [
    "control_attach_rate.csv",
    "control_cycle_exposure.csv",
    "control_base_never_rebilled.csv",
    "control_breakeven_by_channel.csv",
    "control_effective_cac.csv",
    "control_censoring_register.csv",
    "control_decision_contract.csv",
]

# Cards Phase 1 cannot fill. Each one declares what it is blocked on, why the
# metric matters (citing the source) and the phase badge that unblocks it --
# the spec's void convention (section 3.2).
VOID_CARDS = [
    {
        "title": "Rebill rate — cycle 0 → cycle 1",
        "source": "sticky.io #6 · the most-cited subscription metric",
        "blocked": "renewal charge events. The generator emits one kit and one "
                   "price per account; no second charge exists in the warehouse.",
        "unlock": "PHASE 2.2 → MEASURED",
    },
    {
        "title": "Cancellations, pauses and skips — as volume",
        "source": "shopify + crystallize · a named metric of the replenishment model",
        "blocked": "cancellation, pause and skip events with a date and a reason.",
        "unlock": "PHASE 2.1 → MEASURED",
    },
    {
        "title": "Churn rate · Retention rate",
        "source": "all 4 references put it at the top",
        "blocked": "cancellation events. A benchmark there is no way to test: "
                   "&lt;5%/month (Crystallize); 3.9% average in consumer goods (Shopify).",
        "unlock": "PHASE 2.1 → MEASURED",
    },
    {
        "title": "NRR · GRR · Expansion MRR",
        "source": "crystallize · synthesis systems",
        "blocked": "MRR movement decomposition. Phases 2.1–2.3 deliver "
                   "contraction and churned, not expansion — that requires item 2.7.",
        "unlock": "PHASE 2.1 + 2.2 + 2.7 → GRR MEASURED · NRR PENDING",
    },
    {
        "title": "Reactivation rate · Referrals in the first 4 weeks",
        "source": "shopify · the leading predictor of retention",
        "blocked": "referral and resubscription events. No current metric "
                   "reflects a customer choosing to act.",
        "unlock": "PHASE 2.1 + 2.5 → MEASURED",
    },
]


class MissingControlFile(FileNotFoundError):
    """Raised when a control CSV the page depends on is absent."""


def _load(control_dir: Path, filename: str) -> list[dict[str, str]]:
    path = control_dir / filename
    if not path.exists():
        raise MissingControlFile(
            f"{filename} not found in {control_dir}. "
            "Run the Phase 1 `mf query --csv` exports before building the dashboard."
        )
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _pct(raw: str, digits: int = 1) -> str:
    """Format a 0-1 ratio as a percentage. Empty stays an em-dash, never NaN."""
    if raw is None or raw.strip() == "":
        return "—"
    return f"{float(raw) * 100:.{digits}f}%"


def _money(raw: str) -> str:
    if raw is None or raw.strip() == "":
        return "—"
    return "$" + f"{float(raw):,.2f}"


def _num(raw: str, digits: int = 1) -> str:
    if raw is None or raw.strip() == "":
        return "—"
    return f"{float(raw):.{digits}f}"


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _stat_card(title: str, source: str, figure: str, sub: str) -> str:
    return (
        '<div class="card">'
        f"<h3>{_esc(title)}</h3>"
        f'<span class="mid">{_esc(source)}</span>'
        f'<div class="figure">{figure}</div>'
        f'<div class="figsub">{sub}</div>'
        "</div>"
    )


def _void_card(spec: dict[str, str]) -> str:
    return (
        '<div class="card void">'
        f"<h3>{_esc(spec['title'])}</h3>"
        f'<span class="mid">{_esc(spec["source"])}</span>'
        '<div class="figure">not observable</div>'
        f'<p class="blocked"><b>Blocked on:</b> {spec["blocked"]}</p>'
        f'<span class="unlock">{_esc(spec["unlock"])}</span>'
        "</div>"
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        '<details><summary>View table</summary><div class="tablewrap"><table>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody>"
        "</table></div></details>"
    )


def _stylesheet() -> str:
    """Tokens for all three theme states.

    The complete light palette lives on bare `:root`; the dark values are
    redefined under both `@media (prefers-color-scheme: dark)` guarded with
    `:not([data-theme="light"])` and `:root[data-theme="dark"]`, so the viewer's
    explicit toggle wins in both directions and the un-stamped default still
    resolves. No colour is defined only inside a theme block -- that is the
    classic unreadable-page bug.

    Series colours are the validated categorical slots 1 and 2 (blue, orange),
    which clear the lightness band, chroma floor, CVD separation, normal-vision
    floor and contrast checks in both modes.
    """
    return """
:root{color-scheme:light;--plane:#f6f7f4;--surface:#fcfcfb;--sunken:#eeefe9;
--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--hair:rgba(11,11,11,.10);--s1:#2a78d6;--s1-soft:rgba(42,120,214,.12);
--s2:#eb6834;--s2-soft:rgba(235,104,52,.14);--good:#0ca30c;--warning:#fab219;
--critical:#d03b3b;--good-ink:#006300;--critical-ink:#b02c2c;--warning-ink:#8a6100;
--void:rgba(11,11,11,.045);--void-line:rgba(11,11,11,.14);
--sans:system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
--plane:#0c0e0c;--surface:#1a1a19;--sunken:#141513;--ink:#fff;--ink-2:#c3c2b7;
--muted:#898781;--grid:#2c2c2a;--axis:#383835;--hair:rgba(255,255,255,.10);
--s1:#3987e5;--s1-soft:rgba(57,135,229,.18);--s2:#d95926;--s2-soft:rgba(217,89,38,.20);
--good-ink:#0ca30c;--critical-ink:#e37070;--warning-ink:#fab219;
--void:rgba(255,255,255,.045);--void-line:rgba(255,255,255,.16)}}
:root[data-theme="dark"]{color-scheme:dark;--plane:#0c0e0c;--surface:#1a1a19;
--sunken:#141513;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;
--axis:#383835;--hair:rgba(255,255,255,.10);--s1:#3987e5;--s1-soft:rgba(57,135,229,.18);
--s2:#d95926;--s2-soft:rgba(217,89,38,.20);--good-ink:#0ca30c;--critical-ink:#e37070;
--warning-ink:#fab219;--void:rgba(255,255,255,.045);--void-line:rgba(255,255,255,.16)}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font-family:var(--sans);
font-size:15px;line-height:1.5}
.wrap{max-width:1180px;margin:0 auto;padding:32px 24px 72px}
h1{font-size:29px;letter-spacing:-.02em;margin:0;font-weight:640;text-wrap:balance}
.eyebrow{font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.11em;
text-transform:uppercase;color:var(--muted);margin:40px 0 12px}
.band-head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
padding-bottom:10px;border-bottom:1px solid var(--hair);margin-top:44px}
.band-head h2{font-size:21px;font-weight:620;letter-spacing:-.015em;margin:0}
.qmark{font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--muted)}
.grid{display:grid;gap:14px;margin-top:16px;
grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:3px;
padding:16px 18px 14px;display:flex;flex-direction:column;gap:2px;min-width:0}
.card h3{font-size:14px;font-weight:620;margin:0}
.mid{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
.figure{font-size:34px;font-weight:640;letter-spacing:-.022em;margin:10px 0 0}
.figsub{font-size:12.5px;color:var(--ink-2);margin-top:3px}
.void{background:repeating-linear-gradient(135deg,transparent 0 7px,var(--void) 7px 14px),
var(--surface);border:1px dashed var(--void-line)}
.void .figure{color:var(--muted);font-size:20px;font-family:var(--mono);font-weight:600}
.blocked{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:8px;line-height:1.55}
.blocked b{color:var(--ink-2)}
.unlock{display:inline-flex;align-self:flex-start;margin-top:auto;padding:4px 9px;
border-radius:2px;background:var(--s1-soft);color:var(--ink);font-family:var(--mono);
font-size:10.5px;font-weight:700;letter-spacing:.04em}
details{margin-top:12px;border-top:1px solid var(--hair);padding-top:8px}
summary{font-family:var(--mono);font-size:11px;color:var(--muted);cursor:pointer;list-style:none}
summary::before{content:"\\25b8 "}details[open] summary::before{content:"\\25be "}
summary:focus-visible{outline:2px solid var(--s1);outline-offset:2px}
.tablewrap{overflow-x:auto;margin-top:8px}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{text-align:right;padding:5px 9px;border-bottom:1px solid var(--hair);
font-variant-numeric:tabular-nums;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.04em;color:var(--muted);
text-transform:uppercase}
.v-ok{color:var(--good-ink);font-family:var(--mono);font-size:11px;font-weight:700}
.v-trig{color:var(--critical-ink);font-family:var(--mono);font-size:11px;font-weight:700}
.v-none{color:var(--muted);font-family:var(--mono);font-size:11px}
.stamp{font-family:var(--mono);font-size:11px;color:var(--muted)}
footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--hair);
color:var(--ink-2);font-size:13px}
"""


def build_dashboard(control_dir: Path, output_path: Path) -> str:
    """Render the page and write it to `output_path`. Returns the HTML."""
    control_dir = Path(control_dir)

    attach = _load(control_dir, "control_attach_rate.csv")
    exposure = _load(control_dir, "control_cycle_exposure.csv")
    never_rebilled = _load(control_dir, "control_base_never_rebilled.csv")
    breakeven = _load(control_dir, "control_breakeven_by_channel.csv")
    effective = _load(control_dir, "control_effective_cac.csv")
    censoring = _load(control_dir, "control_censoring_register.csv")
    contract = _load(control_dir, "control_decision_contract.csv")

    # --- Band 1 ------------------------------------------------------------
    final_attach = attach[-1]
    band1 = _stat_card(
        "Cumulative attach rate",
        "attach_rate · end of window",
        _pct(final_attach.get("attach_rate", "")),
        f"{_num(final_attach.get('attach_rate_vs_target', ''), 2)}× the launch target",
    )
    band1 += _table(
        ["Week", "Attach rate", "vs. target"],
        [
            [_esc(r.get("weekly_attach_row__signup_week__week", "")),
             _pct(r.get("attach_rate", "")),
             _num(r.get("attach_rate_vs_target", ""), 2) + "×"]
            for r in attach
        ],
    )

    # --- Band 2: the deliberate void ---------------------------------------
    # Read ungrouped, from its own export. The cohort cut cannot answer this
    # question: cohort '0' *is* has_faced_renewal = false, so the ratio's
    # numerator is its own denominator inside it and the row reads 1.0. A card
    # sourced from there prints "100.0%" for "base that has not yet faced a
    # renewal" -- a number that is both wrong and, being a round 100%, unlikely
    # to be doubted. The true share is 11.3%.
    never = never_rebilled[0] if never_rebilled else None
    band2 = _stat_card(
        "Base that has not yet faced a single renewal",
        "pct_base_never_rebilled · ungrouped · derived from signup_date alone",
        _pct(never.get("pct_base_never_rebilled", "") if never else ""),
        "Turns “churn is out of scope” from a caveat into a computed fact.",
    )
    # The shape behind the headline. One number says how much of the base is
    # unobservable; this says how thin the observed part is -- the median
    # account has faced exactly one renewal, which is what bounds every
    # retention reading in the void cards below.
    band2 += _table(
        ["Renewals faced", "Accounts"],
        [
            [_esc(r.get("account__cycle_exposure_cohort", "")),
             _num(r.get("assessable_base_accounts", ""), 0)]
            for r in exposure
        ],
    )
    band2 += "".join(_void_card(c) for c in VOID_CARDS)

    # --- Band 3 ------------------------------------------------------------
    band3 = "".join(
        _stat_card(
            f"Cycles to breakeven — {_esc(r.get('account__channel', ''))}",
            "breakeven_cycles · replaces LTV:CAC in this window",
            _num(r.get("avg_breakeven_cycles", ""), 1),
            _pct(r.get("share_breakeven_cycle_exposed", ""))
            + " of accounts reach breakeven inside the observed window",
        )
        for r in breakeven
    )
    band3 += _table(
        ["Metric", "Denominator", "Excluded", "Share"],
        [
            [_esc(r.get("metric_name", "")),
             r.get("denominator_accounts", ""),
             r.get("excluded_accounts", ""),
             _pct(r.get("excluded_share", ""))]
            for r in censoring
        ],
    )

    # --- Band 4 ------------------------------------------------------------
    band4 = "".join(
        _stat_card(
            f"Effective CAC — {_esc(r.get('effective_cac_row__channel', ''))}",
            "effective_cac · loaded with fulfilment waste",
            _money(r.get("effective_cac", "")),
            "+" + _pct(r.get("cac_uplift_pct", "")) + " over nominal CAC",
        )
        for r in effective
    )

    # --- Decision layer ----------------------------------------------------
    status_class = {"ok": "v-ok", "triggered": "v-trig", "no_data": "v-none"}
    status_label = {"ok": "ok", "triggered": "triggered", "no_data": "no data"}
    contract_rows = [
        [
            _esc(r.get("metric_name", "")),
            _num(r.get("current_value", ""), 3),
            _num(r.get("threshold_value", ""), 3),
            _esc(r.get("action", "")),
            _esc(r.get("owner", "")),
            f'<span class="{status_class.get(r.get("status", ""), "v-none")}">'
            f'{status_label.get(r.get("status", ""), "—")}</span>',
        ]
        for r in contract
    ]
    decision = _table(
        ["Metric", "Value", "Threshold", "Action", "Owner", "Status"], contract_rows
    )

    triggered = sum(1 for r in contract if r.get("status") == "triggered")

    page = f"""<title>PawTrail Decision Board</title>
<style>{_stylesheet()}</style>
<div class="wrap">
<header>
<h1>PawTrail — launch decision board</h1>
<p class="stamp">Generated from dashboard/control_*.csv · {triggered} thresholds triggered</p>
</header>

<p class="eyebrow">Question 1</p>
<div class="band-head"><span class="qmark">Q1</span><h2>Are we growing?</h2></div>
<div class="grid">{band1}</div>

<p class="eyebrow">Question 2</p>
<div class="band-head"><span class="qmark">Q2</span><h2>Do customers stay?</h2></div>
<div class="grid">{band2}</div>

<p class="eyebrow">Question 3</p>
<div class="band-head"><span class="qmark">Q3</span><h2>Are customers valuable?</h2></div>
<div class="grid">{band3}</div>

<p class="eyebrow">Question 4</p>
<div class="band-head"><span class="qmark">Q4</span><h2>Are we acquiring efficiently?</h2></div>
<div class="grid">{band4}</div>

<p class="eyebrow">Decision layer</p>
<div class="band-head"><span class="qmark">·</span><h2>Threshold, action and owner</h2></div>
<div class="card">{decision}</div>

<footer>
<p>Every revenue figure on this page is a <b>modelled entitlement</b>, not collected cash —
no payment event exists in the warehouse.</p>
<p>Band 2 is empty on purpose: the project measures acquisition and onboarding very well,
and does not measure the subscription. Each card declares what unblocks it.</p>
</footer>
</div>
"""
    output_path = Path(output_path)
    output_path.write_text(page, encoding="utf-8")
    return page
