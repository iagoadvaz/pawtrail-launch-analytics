"""Generate the card-by-card Excalidraw explainers.

Run:  python3 dashboard/diagrams/build_diagrams.py
Re-running must produce no diff -- ids are seeded and `updated` is pinned.
"""
import json, random, textwrap, pathlib

random.seed(11)
NOW = 1786900000000  # pinned: regeneration must produce no diff

INK   = "#1e1e1e"; MUTE = "#5c5f66"; RULE = "#adb5bd"
BLUE  = "#1971c2"; GREEN= "#2f9e44"; RED  = "#e03131"; ORANGE="#f08c00"; VIOLET="#6741d9"
BG_CARD="#ffffff"; BG_TILE="#fff9db"; BG_TABLE="#e7f5ff"; BG_CHART="#f8f9fa"; BG_HEAD="#f3f0ff"

def _n(): return random.randint(1, 2**31 - 1)

def _base(t, x, y, w, h, **kw):
    e = {"id": f"e{_n()}", "type": t, "x": round(x,2), "y": round(y,2),
         "width": round(w,2), "height": round(h,2), "angle": 0,
         "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid",
         "strokeWidth": 1, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
         "groupIds": [], "frameId": None, "roundness": None, "seed": _n(),
         "version": 1, "versionNonce": _n(), "isDeleted": False,
         "boundElements": None, "updated": NOW, "link": None, "locked": False}
    e.update(kw); return e

CHARW = {1: 0.56, 2: 0.53, 3: 0.60}

def text(s, x, y, size=14, family=2, color=INK, align="left"):
    lines = s.split("\n")
    w = max((len(l) for l in lines), default=1) * size * CHARW[family] + 2
    h = len(lines) * size * 1.25
    return _base("text", x, y, w, h, strokeColor=color, text=s, originalText=s,
                 fontSize=size, fontFamily=family, textAlign=align,
                 verticalAlign="top", containerId=None, lineHeight=1.25,
                 autoResize=True, roundness=None)

def rect(x, y, w, h, stroke=RULE, bg=BG_CARD, sw=1, style="solid", rough=1):
    return _base("rectangle", x, y, w, h, strokeColor=stroke, backgroundColor=bg,
                 strokeWidth=sw, strokeStyle=style, roughness=rough,
                 roundness={"type": 3})

def line(x, y, w, color=RULE):
    return _base("line", x, y, w, 0, strokeColor=color,
                 points=[[0,0],[round(w,2),0]], lastCommittedPoint=None,
                 startBinding=None, endBinding=None, startArrowhead=None,
                 endArrowhead=None, roundness={"type": 2})

def wrap(s, n): return "\n".join(textwrap.fill(p, n) for p in s.split("\n"))

# ---------------------------------------------------------------- layout ----
CARD_W, GAP, PAD = 620, 44, 18
BODY_CH = 62          # wrap width inside a card
LEAD    = 13          # body font size

def card_elements(c, x, y):
    """Render one card, return (elements, height)."""
    els, cy = [], y + PAD
    kindbg = {"tiles": BG_TILE, "table": BG_TABLE}.get(c["kind"], BG_CHART)
    accent = {"tiles": ORANGE, "table": BLUE}.get(c["kind"], VIOLET)

    els.append(text(c["title"], x + PAD, cy, 17, 1, INK)); cy += 17*1.25 + 3
    els.append(text(f'{c["kind"].upper()}  ·  {c["src"]}', x + PAD, cy, 10, 3, MUTE))
    cy += 10*1.25 + 9
    els.append(line(x + PAD, cy, CARD_W - 2*PAD)); cy += 10

    if c.get("figures"):
        t = wrap(c["figures"], BODY_CH)
        els.append(text(t, x + PAD, cy, 12, 3, accent)); cy += t.count("\n")*12*1.25 + 12*1.25 + 10

    for label, body, col in (("HOW IT IS COMPUTED", c["computed"], BLUE),
                             ("WHY IT MATTERS",     c["why"],      GREEN),
                             ("WHAT GOES WRONG",    c.get("watch"), RED)):
        if not body: continue
        els.append(text(label, x + PAD, cy, 10, 2, col)); cy += 10*1.25 + 4
        t = wrap(body, BODY_CH)
        els.append(text(t, x + PAD, cy, LEAD, 2, INK))
        cy += (t.count("\n") + 1) * LEAD * 1.25 + 11

    h = cy - y + PAD - 6
    els.insert(0, rect(x, y, CARD_W, h, stroke=accent, bg=kindbg, sw=1.5))
    return els, h

def build_scene(tab, cards, subtitle):
    els = []
    els.append(text(tab, 0, 0, 34, 1, INK))
    els.append(text(wrap(subtitle, 108), 0, 52, 14, 2, MUTE))
    top = 52 + (wrap(subtitle,108).count("\n")+1)*14*1.25 + 26
    els.append(line(0, top - 12, CARD_W*2 + GAP, RULE))
    colY = [top, top]
    for c in cards:
        i = 0 if colY[0] <= colY[1] else 1
        x = i * (CARD_W + GAP)
        e, h = card_elements(c, x, colY[i])
        els.extend(e); colY[i] += h + GAP
    return {"type": "excalidraw", "version": 2, "source": "pawtrail-launch-analytics",
            "elements": els, "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {}}

def write(path, scene):
    pathlib.Path(path).write_text(json.dumps(scene, indent=2))
    return len(scene["elements"])

# ---------------------------------------------------------------- cards ----
# Every card on every tab. "watch" entries are defects this project actually
# shipped and fixed -- not hypotheticals.

TABS = []

TABS.append(("01-launch-pulse", "1 · Launch Pulse",
 "Is it growing? Weekly acquisition against the addressable Premium base, and how much of that base each region has reached. Source sheets are named on each card; rebuild each as one Tableau worksheet.", [
 dict(kind="tiles", title="Launch to date", src="control_attach_rate.csv · control_state_saturation.csv",
   figures="Cumulative attach 20.0%  ·  1.33x target  ·  3,000 of 15,000 eligible",
   computed="attach_rate = cumulative_subscriptions / eligible_premium_accounts, read at the LATEST signup week. 'vs launch target' divides that by the 15% target held in a dbt var, so 1.0 means exactly on plan. Subscriptions sums weekly_new_subscriptions across all 17 signup weeks; peak week takes the max of the same column.",
   why="One number for 'is it growing'. The denominator is the addressable Premium base of 15,000, not every Premium account -- an attach rate over a population that was never offered the product measures the offer, not the product.",
   watch="The attach measures are weekly SNAPSHOTS, each already cumulative. Summing all 17 weeks gives 0.1049 against 255,000 'eligible' accounts -- both meaningless. The semantic layer pins them with non_additive_dimension / window_choice: max so any grouping reads the latest week. Fixing this moved attach from 0.1049 to 0.20 and the target ratio from 0.699 to 1.333."),
 dict(kind="chart", title="Cumulative attach rate vs. launch target", src="control_attach_rate.csv",
   computed="Line of attach_rate by signup week, with a flat reference line drawn at the 15% launch target.",
   why="Shows trajectory against plan, and where the crossover happened -- attach passes the target in the week of 16 March and finishes at 1.33x.",
   watch="Plot the rate against a reference LINE. Plotting attach_rate_vs_target as a bar instead reads as on-plan only to someone who already knows the plan; the reader cannot see the target they are being measured against."),
 dict(kind="chart", title="New subscriptions per week", src="control_weekly_new_subscriptions.csv",
   computed="Count of account_id grouped by signup week -- the simple measure subscription_count.",
   why="The volume behind the rate. A cumulative rate rises every week by construction, so it cannot fall even as intake collapses; the weekly bar is the only place a slowdown is visible.",
   watch="Cumulative and weekly series answer different questions and must not share an axis. Read together: attach keeps climbing while weekly intake peaks and declines."),
 dict(kind="chart", title="Penetration of the eligible base, by state", src="control_state_saturation.csv",
   computed="state_penetration = saturation_cumulative_subscriptions / saturation_eligible_accounts, at the end of the launch window.",
   why="Read beside remaining_eligible_accounts. A state decelerating near the ceiling of its own niche is not the same problem as a state nobody has reached -- the first needs a new segment, the second needs spend.",
   watch="Penetration is a per-state ratio and does not average across states. The national figure is the national numerator over the national denominator, never the mean of twelve state rates."),
 dict(kind="chart", title="Attach rate by state, latest week", src="control_attach_rate_by_state.csv",
   computed="attach_rate grouped by state, filtered to the latest signup week so every bar is read at the same snapshot.",
   why="Shows which states are pulling the blended number. Ohio's share of new subscriptions grew fastest of any state -- which is exactly why its fulfilment failure drags the national activation rate.",
   watch="Filter to one week before grouping. Grouping the snapshot measure by state without pinning the week re-introduces the summation bug one dimension down."),
]))

TABS.append(("02-activation", "2 · Activation",
 "Do new accounts get set up? Every rate here is computed on the mature cohort only -- accounts that have had the full window -- so recent signups are excluded rather than scored as failures.", [
 dict(kind="tiles", title="Activation across the mature cohort", src="control_activation_rates.csv",
   figures="30-day activation 71.1% (1.02x the 70% benchmark)  ·  mature cohort 2,661  ·  newest cohort 60.3%, only 76% matured",
   computed="activation_rate_30d = combined_activated_accounts_30d / mature_accounts_30d. Combined means BOTH legs succeeded: a digital login and a kit delivered inside the 10-day SLA. The headline is cohort-weighted across every fully matured week, not the last week's value.",
   why="The launch's North Star. Attach measures whether people bought; activation measures whether the product started working for them. Both legs must succeed, because a delivered kit nobody logs in to and a login with no kit are both failures.",
   watch="Leading with the newest cohort reports CENSORING as performance. That cohort reads 60.3% only because a quarter of it has not finished its 30-day window. The first version of this tile did exactly that and made a healthy launch look like a failing one."),
 dict(kind="chart", title="Activation rates over time", src="control_activation_rates.csv",
   computed="Five series by signup week -- digital_activation_rate_7d, kit_sla_rate, and combined activation at 7, 14 and 30 days -- against a 70% benchmark line. Each divides its own activated count by its OWN mature denominator.",
   why="Separates which leg is failing. Digital activation holds near 65% all window; the combined rate tracks the kit SLA line, which is what identifies fulfilment rather than onboarding as the cause.",
   watch="The five series have five DIFFERENT denominators, because a 7-day window matures sooner than a 30-day one. They are not a funnel and must never be subtracted from each other."),
 dict(kind="chart", title="Time to first login", src="control_login_timing.csv",
   computed="Accounts bucketed into bands by days from signup to first login, plus a separate 'never logged in' band. The companion average, avg_days_to_first_login, averages only accounts that logged in within 30 days.",
   why="A distribution, not an average. The average alone hides that most logins happen in the first days and the rest never happen at all -- two populations that need different interventions.",
   watch="Accounts that never logged in are EXCLUDED from the average, not counted as slow. That is correct (they have no duration to average) but it makes the average optimistic, so the never-logged-in band is shown beside it and cannot hide."),
 dict(kind="table", title="Censoring register — how much of the base each rate excludes", src="control_censoring_register.csv",
   figures="activation_rate_30d: 2,661 in denominator, 339 excluded (11.3%)  ·  7d and kit SLA: 63 excluded (2.1%)",
   computed="One row per published rate: its denominator, how many accounts the maturity gate excluded, and that exclusion as a share of the base.",
   why="Every published rate names the accounts it left out. This is the table that keeps a maturity gate from being read as a performance result -- it converts 'we excluded immature accounts' from a footnote into a number the reader can check.",
   watch="If this table is dropped in the rebuild, every rate on the tab silently becomes a claim about a population the reader cannot see."),
]))

TABS.append(("03-kit-operations", "3 · Kit Operations",
 "Physical fulfilment: on-time delivery, loss and lateness by state. This dashboard carries the launch's clearest operational finding.", [
 dict(kind="tiles", title="Fulfilment headline", src="control_kit_sla_by_state.csv",
   figures="Ohio on-time 51.4%  ·  eleven-state mean 86.2%  ·  gap 34.8 pts  ·  Ohio kit loss 7.2%",
   computed="kit_on_time_delivery_rate = kits_on_time / kits_shipped. BOTH sides are gated on is_mature_sla: the numerator counts kits activated inside the 10-day SLA and matured, the denominator counts every matured kit.",
   why="The single clearest operational finding of the launch. Ohio is not a statistical tail -- it is one carrier relationship, and it is the one fix that moves activation nationally.",
   watch="Drop the maturity gate from the numerator and Ohio reads 52.2% instead of 51.4%: one Ohio kit is on time but has not finished its window. Small here, but it is the same error class that made a whole cohort look like it was failing on the Activation tab."),
 dict(kind="chart", title="On-time delivery rate by state", src="control_kit_sla_by_state.csv",
   computed="kit_on_time_delivery_rate grouped by state, sorted ascending so the worst state is unmissable.",
   why="Sorting is the analysis. Ohio at 51.4% against a next-worst of 84.2% is a different story from a smooth gradient across twelve states, and only the sorted view shows which one you have.",
   watch="An unweighted mean across states is not the national rate -- states differ in volume by two orders of magnitude (California 1,489 matured kits, New Jersey 23). Quote the pooled rate, or say explicitly that the figure is a state mean."),
 dict(kind="chart", title="Kit loss rate by state", src="control_kit_sla_by_state.csv",
   computed="kit_lost_rate = kits_lost / kits_shipped, again on the matured denominator. Ohio 7.2%; five states at 0.0.",
   why="Loss is a distinct failure from lateness and has a distinct owner -- a lost kit is a carrier claim, a late kit is a routing problem.",
   watch="A categorical threshold must reduce direction-aware: max for an 'above' rule, min for a 'below' one. Taking the alphabetically-last row recorded Virginia at 0.0 while Ohio sat at 0.0724 -- that single bug silenced seven thresholds at once. The segment must travel with the value."),
 dict(kind="chart", title="Time to milestone", src="control_time_to_milestone.csv",
   computed="avg_days_to_first_login and avg_days_to_kit_delivery by week. Both average only 30-day-mature accounts that actually reached the milestone within 30 days; nulls are skipped.",
   why="Shows whether the process is slowing before the rate moves -- delivery time drifts up ahead of the SLA rate falling, which makes it the earlier signal.",
   watch="This is a CONDITIONAL average: 'when it happens, how fast', never 'how often it happens'. Read alone it improves when the slowest cases stop arriving at all, so it must be read beside the rate."),
]))

TABS.append(("04-acquisition-efficiency", "4 · Acquisition Efficiency",
 "What each channel costs, once the fulfilment it wastes is loaded back in -- and how many billing cycles that cost takes to repay.", [
 dict(kind="tiles", title="Loaded acquisition cost", src="control_effective_cac.csv",
   figures="self-serve $10.78 effective (+50.9%, $7,641.50 waste)  ·  sales-assisted $29.89 effective (+12.5%, $2,994.00 waste)",
   computed="effective_cac = loaded_spend_usd / new_subscriptions, where loaded spend is marketing spend PLUS fulfilment waste -- the COGS and shipping spent on kits that were lost or went to accounts that never activated. cac_uplift_pct = waste / nominal spend.",
   why="Nominal CAC counts marketing spend only, so a channel that buys cheap accounts which never activate looks like the efficient one. Loading the waste back in is what reveals the real ranking: self-serve's cost is understated by half.",
   watch="waste_reason is an ordered CASE, not two rows. An account that lost its kit AND failed to activate consumed ONE kit, not two -- lost kit wins because it is the root cause of the non-activation."),
 dict(kind="chart", title="Nominal vs. effective CAC by channel", src="control_effective_cac.csv",
   computed="Paired bars per channel: marketing-only CAC beside waste-loaded CAC.",
   why="The gap between the pair IS the finding. Showing effective CAC alone loses the comparison that makes it meaningful.",
   watch="Never put the two on separate axes to make the bars similar heights. One axis, or the visual comparison the chart exists for is destroyed."),
 dict(kind="chart", title="Cycles to break even, by channel", src="control_breakeven_by_channel.csv",
   figures="self-serve 1.13 cycles (92.9% exposed)  ·  sales-assisted 2.44 cycles (79.0% exposed)",
   computed="avg_breakeven_cycles = breakeven_cycles_sum / unit_economics_accounts, using observed contribution margin only -- no survival curve, no assumed lifetime. share_breakeven_cycle_exposed = accounts whose breakeven cycle actually came due inside the window / all accounts.",
   why="The honest substitute for LTV:CAC inside a 120-day window. LTV needs a retention curve this window cannot supply; cycles-to-repay needs only what has already been billed.",
   watch="The exposed share is the censoring column, not a footnote. Without it the average silently mixes accounts that provably repaid with accounts whose payback cycle has not arrived -- and the more recent the cohort, the more it flatters."),
 dict(kind="chart", title="Cost per activated account, by channel and week", src="control_cac_by_channel.csv",
   figures="self-serve $4.64 -> $13.07 and sales-assisted $12.65 -> $37.73 between the 2 March and 30 March cohorts",
   computed="channel_activation_measurable_spend_usd / channel_estimated_activated_subscriptions -- spend divided by accounts that went on to activate, not merely to sign up.",
   why="A quality-adjusted CAC. It punishes a channel that acquires accounts cheaply but never activates them, and it is where the Ohio fulfilment failure surfaces in the unit economics: raw CAC rose 2.3x over the stretch while cost per activated rose 2.8x.",
   watch="Weeks with spend but no subscriptions must stay in the mart. Dropping them hid $2,732.38 -- 7.0% of all marketing spend -- and understated CAC in both channels. The fix builds the mart on a spine of every channel-week that appears in EITHER subscriptions or spend."),
 dict(kind="table", title="Unit economics by channel", src="control_breakeven_by_channel.csv · control_effective_cac.csv",
   computed="One row per channel: effective CAC, contribution margin per cycle, average breakeven cycles, and the exposed share.",
   why="The table is where the two charts reconcile. A reader who distrusts a bar can check the arithmetic here.",
   watch=None),
]))

TABS.append(("05-retention-lifecycle", "5 · Retention & Lifecycle",
 "Renewal behaviour across the billing cycles that came due inside the window. Every measure here is per cycle -- a figure blended across cycles mixes a survival curve with an incremental hazard.", [
 dict(kind="tiles", title="Renewal exposure", src="control_base_never_rebilled.csv · control_lifecycle_by_cycle.csv",
   figures="11.3% of the base never rebilled (339 of 3,000)  ·  GRR 0.931 and NRR 0.934 at the latest cycle",
   computed="pct_base_never_rebilled = renewal_unexposed_accounts / assessable_base_accounts. GRR = (starting - churned - contraction) / starting; NRR adds expansion to the numerator.",
   why="It turns 'churn is out of scope because we only have 120 days' from a prose caveat into a computed fact: 11.3% of accounts have not yet faced a single renewal, so no retention figure can speak for them.",
   watch="Read pct_base_never_rebilled UNGROUPED. Grouped by cycle_exposure_cohort the numerator becomes its own denominator inside cohort '0' and the card reads a tautological 100.0%. The first build of this card did exactly that."),
 dict(kind="chart", title="Survival and churn hazard by cycle", src="control_lifecycle_by_cycle.csv",
   computed="retention_rate = retained_accounts / cycle_rows -- cumulative survival, counting skipped and paused accounts as retained. monthly_churn_rate = churned_accounts / accounts that entered the cycle ALIVE.",
   why="Survival and hazard answer different questions: how many are left, versus how dangerous this particular cycle is. Plotting both shows that the risk is concentrated in cycle 1 rather than spread evenly.",
   watch="The hazard denominator is the at-risk population, not every row at that cycle. Accounts that cancelled earlier are carried forward in the spine and had no opportunity to churn again; leaving them in understates the hazard by 24% at cycle 2 and 31% at cycle 3 -- and worse, it flattens the curve's shape, the one property that matters."),
 dict(kind="chart", title="Skip and pause, by renewal cycle", src="control_skip_and_pause.csv",
   figures="cycle 1 skip 5.9% / pause 2.4%  ·  cycle 2 4.8% / 3.0%  ·  cycle 3 6.2% / 5.6%",
   computed="skip_rate = skipped_cycles / RENEWAL cycle rows; pause_rate likewise. Cycle 0 is excluded from the denominator entirely.",
   why="Skip and pause are retention signals that are not churn -- a paused subscription is still a customer. Reported separately they show engagement softening before cancellation does.",
   watch="Cycle 0 is a signup, not a renewal: nobody can skip a shipment they were never due. Including its 3,000 structurally-zero rows in the denominator understated both rates by 41% -- skip read 0.0328 instead of 0.0554. The metric matched an independent recomputation because the recomputation repeated the same definitional error; only naming the denominator caught it."),
 dict(kind="chart", title="MRR movement by cycle", src="control_mrr_movement.csv",
   computed="starting + new + expansion - contraction - churned = ending, computed on subscription VALUE at the tier in force rather than on cash billed. Deferred billings are published beside the bridge, never inside it.",
   why="Value-based means a skip does not look like a downgrade. A skipped shipment defers revenue; it does not change what the subscription is worth, so it must not enter contraction.",
   watch="Built on cash billed instead, cycle 1 contraction reads $6,387.79 -- of which $6,247.79 is deferred billing and only $140.00 is a genuine downgrade. That single choice moved GRR from 0.685 to 0.770 and NRR from 0.796 to 0.931."),
 dict(kind="table", title="Lifecycle by cycle", src="control_lifecycle_by_cycle.csv · control_mrr_movement.csv",
   computed="One row per cycle: rebill rate, retention, hazard, and the MRR bridge components.",
   why="Lets a reader verify that the bridge closes -- starting plus movements equals ending, exactly, at every cycle.",
   watch=None),
]))

TABS.append(("06-cs-queue", "6 · CS Queue",
 "Who to call on Monday. The queue is split two ways: by which leg failed, and by whether the company caused the damage.", [
 dict(kind="tiles", title="Outreach queue", src="control_at_risk_by_driver.csv · control_at_risk_by_damage_class.csv",
   figures="944 accounts at risk  ·  448 system-inflicted, $12,455.52 recoverable MRR  ·  485 ambiguous  ·  11 self-selected",
   computed="is_at_risk = no_digital_access_14d OR kit_failed_sla OR no_tasks_completed. recoverable_mrr_usd carries the account's monthly price when it is at risk, and is null otherwise.",
   why="Turns a count into a prioritised budget. '944 accounts' is not workable; '448 accounts worth $12,455 a month, whose kits we failed to deliver' is a Monday morning call list.",
   watch="Sum recoverable MRR only over at-risk accounts -- the column is deliberately null elsewhere so a careless SUM cannot quietly include healthy accounts."),
 dict(kind="chart", title="At-risk accounts by failure driver", src="control_at_risk_by_driver.csv",
   figures="496 digital failure  ·  352 physical failure  ·  96 both legs failed",
   computed="COUNTS of at-risk accounts grouped by risk_driver, which records which leg failed.",
   why="Says which team owns the remediation: a digital failure is onboarding's, a physical failure is fulfilment's, and 96 accounts need both.",
   watch="Plot counts, never a rate. risk_driver is assigned from the same flags that DEFINE at-risk, so the at-risk rate is 1.0 in every bucket by construction and carries no information at all."),
 dict(kind="chart", title="At-risk rate by state", src="control_at_risk_by_state.csv",
   figures="Ohio 57.4%  ·  New Jersey 52.2%  ·  Virginia 25.8%",
   computed="at_risk_account_rate = at_risk_accounts / assessable accounts, grouped by state.",
   why="This is where a rate belongs -- the denominator is a genuinely different population, so the ratio carries information. It also confirms the Ohio finding from a second, independent direction.",
   watch="Assessable, not all accounts: an account too new to have failed a 14-day check has had no opportunity to be at risk and must not sit in the denominator."),
 dict(kind="table", title="Damage classification", src="control_at_risk_by_damage_class.csv",
   computed="Ordered CASE: any kit SLA failure -> system_inflicted; else never logged in AND Premium tenure <= 365 days -> self_selected; else ambiguous.",
   why="risk_driver says WHICH leg failed; damage_class says WHETHER IT IS WORTH ACTING ON. Prioritise system-inflicted -- those accounts failed because of a delivery failure the company owns, which makes the outreach credible rather than annoying.",
   watch="The tenure threshold is calibrated, not assumed. An absolute 180-day cut yields FOUR accounts base-wide and collapses the class to zero, leaving an unworkable two-bucket list. That only 11 accounts land in self_selected is itself the finding: tenure does not discriminate in this data."),
]))

TABS.append(("07-decision-contract", "7 · Decision Contract",
 "Every published metric with a threshold set before the value was observed, the segment that value came from, and the action its owner takes when it fires. This is the sheet that makes the analysis falsifiable.", [
 dict(kind="tiles", title="Contract state", src="control_decision_contract.csv",
   figures="29 metrics under contract  ·  17 triggered  ·  12 within tolerance  ·  0 rows unresolved",
   computed="One row per metric: current value, the segment that value came from, a threshold, a direction, a status, an owner and an action. Status is triggered when the value crosses the threshold in the declared direction.",
   why="A dashboard that only reports numbers cannot be wrong. Declaring the threshold and the consequence BEFORE observing the value is what makes the analysis falsifiable -- and 17 of 29 firing is a finding, not a failure of the contract.",
   watch="Every row must resolve to a real value. A metric declared in the contract but never produced by the semantic layer leaves a row that can never fire -- an alarm wired to nothing, which reads as safety."),
 dict(kind="table", title="Four tables, one per decision question", src="control_decision_contract.csv",
   figures="Is it growing?  ·  Are they staying?  ·  Is it valuable?  ·  Is it efficient?",
   computed="The same 29 rows split by decision_question, so each table answers exactly one question a launch review asks.",
   why="Organised around the questions the review asks, not around the models that happen to exist. A reader looking for 'are they staying' should not have to know which mart the answer lives in.",
   watch="The segment column is not decoration. A row reading 'kit_lost_rate 0.072, triggered, audit the carrier' is not actionable until it also says OH -- without the segment, nobody knows where to send the auditor."),
 dict(kind="table", title="The two rules that govern the contract", src="WORKBOOK_SPEC.md",
   computed="Rule 1: a categorical threshold is written to catch the WORST segment, so the reduction is direction-aware -- max for an 'above' rule, min for a 'below' one. Rule 2: thresholds are fixed before the value is read.",
   why="Rule 2 is what separates analysis from storytelling. If a metric does not trigger, the finding IS the metric; a threshold moved to fit an observation cannot afterwards be evidence about that observation.",
   watch="Breaking rule 1 is silent. Reducing a categorical metric to its alphabetically-last row recorded Virginia at 0.0 while Ohio sat at 0.0724 -- seven thresholds went quiet at once and the dashboard looked healthier for it."),
]))

# ----------------------------------------------------------------- main ----

OUT = pathlib.Path("/home/iagoadvaz/projects/pawtrail-launch-analytics/dashboard/diagrams")
OUT.mkdir(exist_ok=True)

def arrow(x, y, w):
    return _base("arrow", x, y, w, 0, strokeColor=MUTE,
                 points=[[0,0],[round(w,2),0]], lastCommittedPoint=None,
                 startBinding=None, endBinding=None, startArrowhead=None,
                 endArrowhead="arrow", roundness={"type": 2})

# ------------------------------------------------------------ overview ------
def overview():
    els = []
    els.append(text("PawTrail Launch Workbook — how every card is computed", 0, 0, 32, 1, INK))
    els.append(text(wrap("One Excalidraw file per Tableau dashboard. Each card panel states how the metric is "
                         "computed, why it matters, and -- where this project shipped the mistake once -- what "
                         "goes wrong if you compute it the obvious way instead.", 110), 0, 50, 14, 2, MUTE))
    y = 128
    els.append(text("THE PIPELINE EVERY NUMBER COMES THROUGH", 0, y, 11, 2, VIOLET)); y += 26
    stages = [("Synthetic\ngenerator", BG_CHART), ("DuckDB\nraw", BG_CHART),
              ("dbt marts\nstaging - int - marts", BG_CHART),
              ("MetricFlow\n50 metrics", BG_TILE),
              ("control_*.csv\n25 extracts", BG_TABLE),
              ("Tableau\n7 dashboards", BG_HEAD)]
    x, bw, bh = 0, 195, 66
    for i, (lab, bg) in enumerate(stages):
        els.append(rect(x, y, bw, bh, stroke=VIOLET if i >= 3 else RULE, bg=bg, sw=1.5))
        els.append(text(lab, x + 14, y + 16, 13, 2, INK))
        if i < len(stages) - 1:
            els.append(arrow(x + bw + 8, y + bh/2, 44))
        x += bw + 60
    y += bh + 46
    els.append(line(0, y, 1284)); y += 22

    els.append(text("THE SEVEN TABS", 0, y, 11, 2, VIOLET)); y += 26
    rows = [
      ("1  Launch Pulse",  "Is it growing?",   "5 cards", "Attach finishes at 20.0% — 1.33x the 15% target."),
      ("2  Activation",    "Do they set up?",  "4 cards", "71.1% across 2,661 matured accounts; the newest cohort's 60.3% is censoring, not decline."),
      ("3  Kit Operations","Does the kit land?","4 cards","Ohio 51.4% on-time vs an 86.2% eleven-state mean — the launch's clearest finding."),
      ("4  Acquisition",   "Is it efficient?", "5 cards", "Loading fulfilment waste back in raises self-serve CAC by 50.9%."),
      ("5  Retention",     "Are they staying?","5 cards", "11.3% of the base has never faced a renewal — churn's scope, computed."),
      ("6  CS Queue",      "Who do we call?",  "4 cards", "448 of 944 at-risk accounts are system-inflicted: $12,455/mo recoverable."),
      ("7  Decision Contract","Can it be wrong?","3 cards","29 metrics with thresholds set before the values were read; 17 triggered."),
    ]
    for name, q, n, finding in rows:
        h = 62
        els.append(rect(0, y, 1284, h, stroke=RULE, bg=BG_CHART, sw=1))
        els.append(text(name, 16, y + 12, 15, 1, INK))
        els.append(text(q, 250, y + 14, 12, 2, BLUE))
        els.append(text(n, 430, y + 14, 11, 3, MUTE))
        els.append(text(wrap(finding, 84), 520, y + 12, 12, 2, INK))
        y += h + 12
    y += 18
    els.append(line(0, y, 1284)); y += 22
    els.append(text("THREE CONVENTIONS THAT ARE LOAD-BEARING", 0, y, 11, 2, RED)); y += 26
    conv = [
      ("Reference lines, not ratio bars",
       "Attach plots against a 15% target line and activation against a 70% benchmark. Plotting "
       "attach_rate_vs_target as a bar reads as on-plan only to someone who already knows the plan."),
      ("The headline is the cohort-weighted rate, never the newest cohort",
       "30-day activation reads 71.1% across all matured accounts. The newest cohort reads 60.3% only "
       "because a quarter of it has not finished its window; leading with it reports censoring as performance."),
      ("Counts where a rate would be tautological",
       "The CS queue splits by driver as counts, because risk_driver is assigned from the same flags that "
       "define at-risk — a rate there is 1.0 in every bucket by construction. The rate goes on the state cut."),
    ]
    bw2 = 412
    wrapped = [(wrap(t, 42), wrap(b, 50)) for t, b in conv]
    hh = max(12 + (t.count("\n") + 1) * 13 * 1.25 + 8
             + (b.count("\n") + 1) * 12 * 1.25 + 16 for t, b in wrapped)
    for i, (t, b) in enumerate(wrapped):
        x = i * (bw2 + 24)
        els.append(rect(x, y, bw2, hh, stroke=RED, bg="#fff5f5", sw=1.5))
        els.append(text(t, x + 14, y + 12, 13, 1, INK))
        els.append(text(b, x + 14, y + 12 + (t.count("\n") + 1) * 13 * 1.25 + 8, 12, 2, INK))
    return {"type": "excalidraw", "version": 2, "source": "pawtrail-launch-analytics",
            "elements": els, "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {}}

total = 0
n = write(OUT / "00-overview.excalidraw", overview())
print(f"  00-overview.excalidraw            {n:4d} elements"); total += n
for slug, title, lede, cards in TABS:
    scene = build_scene(title, cards, lede)
    n = write(OUT / f"{slug}.excalidraw", scene)
    print(f"  {slug}.excalidraw{' '*(30-len(slug))}{n:4d} elements  ({len(cards)} cards)")
    total += n
print(f"\n{total} elements across {len(TABS)+1} files")
