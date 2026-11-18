import io
import itertools
import json
import unittest
from datetime import date, datetime, timedelta, timezone

from pypdf import PdfReader

from farmsense_core import alerts, capacity, partitions, replay
from farmsense_core.aggregation import bucketize, detect_gaps, median_filter, rate_per_minute
from farmsense_core.alerts import ABOVE, BELOW, NO_DATA, RATE_ABOVE, Evaluator, Rule, run_series
from farmsense_core.devices import generate_device_key, hash_secret, sign_body, split_key, verify_device_key, verify_signature
from farmsense_core.ingest import MAX_BATCH, parse_batch, parse_timestamp
from farmsense_core.insights import (InvalidInsight, SAFE_REFERRAL, build_prompt, facts_from_report, fallback_insight, validate_insight)
from farmsense_core.permissions import (ALL_ACTIONS, GRANTS, OWNER, ROLES, SITE_ACTIONS, Membership, can, can_assign_role,
                                        can_change_member, visible_sites)
from farmsense_core.reports import SensorMeta, build_daily_report, local_day_bounds, render_pdf, render_text
from farmsense_core.sensors import normalize_value
from farmsense_core.simulator import simulate_temperature

UTC = timezone.utc
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class SensorTests(unittest.TestCase):
    def test_units_are_converted_and_rounded(self):
        self.assertEqual(normalize_value("temperature", 86, "F"), 30.0)
        self.assertEqual(normalize_value("temperature", 300.15, "K"), 27.0)
        self.assertEqual(normalize_value("water_level", 1.5, "m"), 150.0)
        self.assertEqual(normalize_value("temperature", 21.456), 21.5)

    def test_physical_nonsense_is_refused(self):
        for bad, reason in [(85.0, "out_of_range"), (-60, "out_of_range"), (float("nan"), "invalid_value"), (float("inf"), "invalid_value"),
                            ("21", "invalid_value"), (True, "invalid_value"), (None, "invalid_value")]:
            with self.assertRaises(ValueError) as cm:
                normalize_value("temperature", bad)
            self.assertEqual(str(cm.exception), reason)
        with self.assertRaises(ValueError):
            normalize_value("temperature", 20, "furlongs")
        with self.assertRaises(ValueError):
            normalize_value("radiation", 1)
        with self.assertRaises(ValueError):
            normalize_value("humidity", 101)


class IngestTests(unittest.TestCase):
    SENSORS = {"barn1-temp": "temperature", "barn1-hum": "humidity"}

    def batch(self, *items, now=T0):
        return parse_batch({"readings": list(items)}, self.SENSORS, now)

    def test_good_and_bad_readings_are_separated_with_reasons(self):
        r = self.batch(
            {"sensor": "barn1-temp", "ts": "2026-11-11T11:59:00Z", "value": 24.3},
            {"sensor": "barn1-temp", "ts": "2026-11-11T11:58:00+01:00", "value": 75.0, "unit": "F"},
            {"sensor": "other-farm-temp", "ts": "2026-11-11T11:59:00Z", "value": 20},
            {"sensor": "barn1-temp", "ts": "2026-11-11T11:59:00", "value": 20},
            {"sensor": "barn1-temp", "ts": "2026-11-11T12:30:00Z", "value": 20},
            {"sensor": "barn1-temp", "ts": "2026-10-01T00:00:00Z", "value": 20},
            {"sensor": "barn1-hum", "ts": "2026-11-11T11:59:00Z", "value": 140},
            {"sensor": "barn1-temp", "ts": "2026-11-11T11:59:00Z", "value": 24.3})
        self.assertEqual(len(r.accepted), 2)
        self.assertEqual([x.reason for x in r.rejected], ["unknown_sensor", "bad_timestamp", "in_future", "too_old", "out_of_range", "duplicate_in_batch"])
        self.assertEqual(r.accepted[1].value, 23.9)
        self.assertEqual(r.summary()["rejected"], 6)

    def test_a_device_cannot_write_to_a_sensor_it_does_not_own(self):
        r = self.batch({"sensor": "someone-elses", "ts": "2026-11-11T11:59:00Z", "value": 20})
        self.assertEqual(r.rejected[0].reason, "unknown_sensor")

    def test_late_data_is_kept_but_flagged(self):
        r = self.batch({"sensor": "barn1-temp", "ts": "2026-11-11T11:00:00Z", "value": 20},
                       {"sensor": "barn1-temp", "ts": "2026-11-11T11:55:00Z", "value": 21})
        self.assertEqual([x.late for x in r.accepted], [True, False])

    def test_timestamp_formats(self):
        self.assertEqual(parse_timestamp(1_794_000_000), parse_timestamp(1_794_000_000_000))
        self.assertEqual(parse_timestamp("2026-11-11T12:00:00Z"), T0)
        for bad in ("yesterday", "2026-11-11", None, True, 1e30):
            with self.assertRaises(ValueError):
                parse_timestamp(bad)

    def test_batch_level_errors(self):
        with self.assertRaises(ValueError):
            parse_batch({"readings": "nope"}, self.SENSORS, T0)
        with self.assertRaises(ValueError):
            parse_batch({"readings": [{}] * (MAX_BATCH + 1)}, self.SENSORS, T0)
        self.assertEqual(self.batch("not a dict").rejected[0].reason, "invalid_value")


class DeviceTests(unittest.TestCase):
    def test_key_roundtrip_and_storage_holds_only_a_hash(self):
        key_id, stored_hash, full = generate_device_key()
        self.assertEqual(split_key(full)[0], key_id)
        self.assertNotIn(split_key(full)[1], stored_hash)
        self.assertEqual(verify_device_key(full, {key_id: stored_hash}.get), key_id)

    def test_wrong_secret_unknown_id_and_malformed_keys_fail(self):
        key_id, stored_hash, full = generate_device_key()
        lookup = {key_id: stored_hash}.get
        for bad in (full[:-1] + ("A" if full[-1] != "A" else "B"), f"fsk_deadbeef_{split_key(full)[1]}", "garbage", "", None, "fsk__x", "xyz_a_b"):
            self.assertIsNone(verify_device_key(bad, lookup))

    def test_revoking_a_key_stops_that_device_only(self):
        a, ha, ka = generate_device_key()
        b, hb, kb = generate_device_key()
        db = {a: ha, b: hb}
        db.pop(a)
        self.assertIsNone(verify_device_key(ka, db.get))
        self.assertEqual(verify_device_key(kb, db.get), b)

    def test_signature_detects_tampering_and_replay(self):
        body, ts = b'{"readings": []}', 1_794_000_000
        sig = sign_body("shared", ts, body)
        self.assertTrue(verify_signature("shared", ts, body, sig, now=ts + 10))
        self.assertFalse(verify_signature("shared", ts, body + b" ", sig, now=ts + 10))
        self.assertFalse(verify_signature("other", ts, body, sig, now=ts + 10))
        self.assertFalse(verify_signature("shared", ts, body, sig, now=ts + 3600))


class AggregationTests(unittest.TestCase):
    def test_buckets(self):
        pts = [(T0 + timedelta(minutes=m), float(m)) for m in range(0, 20)]
        b = bucketize(pts, 600)
        self.assertEqual([x.count for x in b], [10, 10])
        self.assertEqual((b[0].minimum, b[0].maximum, b[0].avg), (0.0, 9.0, 4.5))
        self.assertEqual(b[0].start.minute % 10, 0)

    def test_median_filter_removes_a_spike_but_keeps_a_step(self):
        self.assertEqual(median_filter([20, 20, 99, 20, 20]), [20, 20, 20, 20, 20])
        self.assertEqual(median_filter([20, 20, 20, 30, 30, 30, 30]), [20, 20, 20, 30, 30, 30, 30])
        with self.assertRaises(ValueError):
            median_filter([1, 2], window=4)

    def test_gaps_and_rate(self):
        ts = [T0 + timedelta(minutes=m) for m in (0, 1, 2, 3, 40, 41)]
        self.assertEqual(detect_gaps(ts, 60), [(ts[3], ts[4])])
        self.assertAlmostEqual(rate_per_minute((T0, 20.0), (T0 + timedelta(minutes=5), 25.0)), 1.0)
        self.assertEqual(rate_per_minute((T0, 1), (T0, 2)), 0.0)


def feed(ev: Evaluator, values, start=T0, step=60):
    events, t = [], start
    for v in values:
        events += ev.step(t, v)
        t += timedelta(seconds=step)
    return events


class AlertTests(unittest.TestCase):
    RULE = Rule("hot", ABOVE, 30.0, for_seconds=300, clear_threshold=29.0, cooldown_seconds=600, escalate_after_seconds=1200)

    def test_a_short_spike_never_fires(self):
        self.assertEqual(feed(Evaluator(self.RULE), [25, 25, 40, 25, 25, 25]), [])

    def test_sustained_breach_fires_once_after_the_wait(self):
        ev = feed(Evaluator(self.RULE), [31] * 10)
        self.assertEqual([e.kind for e in ev], ["fire"])
        self.assertEqual(ev[0].at, T0 + timedelta(minutes=5))

    def test_hysteresis_prevents_flapping(self):
        wobble = [31] * 6 + [29.5, 30.5] * 10 + [28] * 3
        with_h = feed(Evaluator(self.RULE), wobble)
        self.assertEqual([e.kind for e in with_h if e.kind in ("fire", "resolve")], ["fire", "resolve"])
        no_h = Rule("hot", ABOVE, 30.0, for_seconds=0, cooldown_seconds=10 ** 6)
        flappy = feed(Evaluator(no_h), wobble)
        self.assertGreater(sum(e.kind == "fire" for e in flappy), 5)

    def test_reminders_respect_cooldown_and_stop_when_acknowledged(self):
        ev = Evaluator(Rule("hot", ABOVE, 30.0, cooldown_seconds=600))
        events = feed(ev, [31] * 31)
        self.assertEqual([e.kind for e in events], ["fire"] + ["reminder"] * 3)
        ev2 = Evaluator(Rule("hot", ABOVE, 30.0, cooldown_seconds=600))
        feed(ev2, [31] * 3)
        ev2.acknowledge()
        self.assertEqual(feed(ev2, [31] * 40, start=T0 + timedelta(minutes=3)), [])

    def test_escalation_happens_once_and_only_if_nobody_acknowledges(self):
        r = Rule("hot", ABOVE, 30.0, cooldown_seconds=10 ** 6, escalate_after_seconds=600)
        events = feed(Evaluator(r), [31] * 40)
        self.assertEqual([e.kind for e in events], ["fire", "escalate"])
        ev = Evaluator(r)
        feed(ev, [31] * 5)
        ev.acknowledge()
        self.assertEqual([e.kind for e in feed(ev, [31] * 30, start=T0 + timedelta(minutes=5))], [])

    def test_a_resolved_alert_can_fire_again(self):
        events = feed(Evaluator(Rule("hot", ABOVE, 30.0)), [31, 31, 28, 28, 31, 31])
        self.assertEqual([e.kind for e in events], ["fire", "resolve", "fire"])

    def test_below_rule(self):
        events = feed(Evaluator(Rule("cold", BELOW, 5.0, for_seconds=120, clear_threshold=7.0)), [4, 4, 4, 4, 6, 7.5])
        self.assertEqual([e.kind for e in events], ["fire", "resolve"])

    def test_rate_rule_catches_a_fast_rise(self):
        events = feed(Evaluator(Rule("fast", RATE_ABOVE, 1.0)), [20, 20.2, 20.4, 23, 26, 26.1])
        self.assertTrue(events and events[0].kind == "fire")

    def test_no_data_rule_fires_after_silence_and_resolves_on_return(self):
        ev = Evaluator(Rule("offline", NO_DATA, for_seconds=600))
        events = feed(ev, [20, 20] + [None] * 15 + [20])
        self.assertEqual([e.kind for e in events], ["fire", "resolve"])
        self.assertEqual(events[0].at, T0 + timedelta(minutes=1 + 10))

    def test_no_data_rule_is_quiet_before_the_first_reading(self):
        self.assertEqual(feed(Evaluator(Rule("offline", NO_DATA, for_seconds=60)), [None] * 30), [])

    def test_missing_tick_does_not_resolve_a_firing_alert(self):
        events = feed(Evaluator(Rule("hot", ABOVE, 30.0, cooldown_seconds=10 ** 6)), [31, None, None, 31])
        self.assertEqual([e.kind for e in events], ["fire"])

    def test_run_series_with_smoothing_ignores_single_glitches(self):
        pts = [(T0 + timedelta(minutes=m), 25.0) for m in range(30)]
        pts[10] = (pts[10][0], 55.0)
        self.assertEqual(run_series(Rule("hot", ABOVE, 30.0), pts, smooth=1)[0].kind, "fire")
        self.assertEqual(run_series(Rule("hot", ABOVE, 30.0), pts, smooth=5), [])


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = replay.scenario()
        cls.events = {r.name: run_series(r, cls.samples, smooth=5 if r is not replay.NAIVE else 1,
                                         ack_at=replay.ACK_AT if r is not replay.NAIVE else None) for r in replay.RULES + [replay.NAIVE]}

    def test_scenario_is_deterministic(self):
        self.assertEqual(replay.scenario(), replay.scenario())
        self.assertEqual(len(self.samples), 4280)

    def test_real_rules_fire_once_each_for_the_heat_wave_and_not_for_glitches(self):
        for name in ("High temperature", "Critical temperature"):
            fires = [e for e in self.events[name] if e.kind == "fire"]
            self.assertEqual(len(fires), 1)
            self.assertEqual(fires[0].at.day, 10)

    def test_heat_wave_is_detected_within_half_an_hour(self):
        onset = next(ts for ts, v in self.samples if ts > replay.START + timedelta(days=1, hours=12) and v > 30)
        fire = next(e.at for e in self.events["High temperature"] if e.kind == "fire")
        self.assertLess(fire - onset, timedelta(minutes=30))

    def test_dropout_is_noticed_and_resolved(self):
        kinds = [e.kind for e in self.events["Sensor offline"]]
        self.assertEqual(kinds, ["fire", "resolve"])

    def test_naive_rule_is_an_alert_storm(self):
        naive = self.events[replay.NAIVE.name]
        real = sum(len(v) for k, v in self.events.items() if k != replay.NAIVE.name)
        self.assertGreater(len(naive), 20 * real)


class PermissionTests(unittest.TestCase):
    def test_every_action_is_granted_to_somebody_and_nothing_to_nobody(self):
        self.assertFalse(can(None, "dashboard.view"))
        self.assertFalse(can(Membership("owner"), "launch.missiles"))

    def test_the_operational_roles_form_a_strict_ladder(self):
        self.assertLess(GRANTS["worker"], GRANTS["supervisor"])
        self.assertLess(GRANTS["supervisor"], GRANTS["manager"])
        self.assertLess(GRANTS["manager"], GRANTS["owner"])

    def test_viewer_and_advisor_sit_beside_the_ladder_not_on_it(self):
        self.assertFalse(GRANTS["viewer"] <= GRANTS["worker"], "viewers can read reports, workers cannot")
        self.assertTrue({"insight.view", "insight.request"} <= GRANTS["advisor"])
        self.assertFalse("alert.ack" in GRANTS["advisor"])

    def test_dangerous_actions_belong_to_the_top_only(self):
        for role in ROLES:
            m = Membership(role)
            self.assertEqual(can(m, "billing.manage"), role == "owner")
            self.assertEqual(can(m, "farm.delete"), role == "owner")
            self.assertEqual(can(m, "member.manage"), role in ("owner", "manager"))
            self.assertEqual(can(m, "alert.rule.manage"), role in ("owner", "manager"))

    def test_viewers_and_advisors_never_change_anything(self):
        writes = {"alert.ack", "alert.rule.manage", "device.manage", "member.manage", "report.configure", "billing.manage", "farm.update", "farm.delete"}
        for role in ("viewer", "advisor"):
            self.assertFalse(any(can(Membership(role), a) for a in writes))

    def test_workers_can_acknowledge_but_not_configure(self):
        w = Membership("worker")
        self.assertTrue(can(w, "alert.ack"))
        self.assertFalse(can(w, "alert.rule.manage"))
        self.assertFalse(can(w, "readings.export"))

    def test_site_scoped_members_see_only_their_sites_and_no_farm_wide_actions(self):
        m = Membership("supervisor", frozenset({1, 2}))
        self.assertTrue(can(m, "dashboard.view", 1))
        self.assertFalse(can(m, "dashboard.view", 3))
        self.assertFalse(can(m, "dashboard.view"), "a site action with no site must be denied for a scoped member")
        self.assertFalse(can(m, "report.view"), "farm-wide reports need a farm-wide membership")
        self.assertEqual(visible_sites(m, [1, 2, 3]), frozenset({1, 2}))
        self.assertEqual(visible_sites(Membership("owner"), [1, 2, 3]), frozenset({1, 2, 3}))
        self.assertEqual(visible_sites(None, [1, 2, 3]), frozenset())

    def test_even_a_scoped_manager_cannot_manage_members(self):
        self.assertFalse(can(Membership("manager", frozenset({1})), "member.manage", 1))

    def test_exhaustive_site_scoping_rule(self):
        for role, action in itertools.product(ROLES, ALL_ACTIONS):
            scoped = Membership(role, frozenset({7}))
            if can(scoped, action, 7):
                self.assertIn(action, SITE_ACTIONS)
                self.assertTrue(can(Membership(role), action))
            self.assertFalse(can(scoped, action, 8))

    def test_no_privilege_escalation_through_role_assignment(self):
        mgr, own = Membership("manager"), Membership("owner")
        self.assertTrue(can_assign_role(mgr, "worker"))
        for forbidden in ("manager", "owner"):
            self.assertFalse(can_assign_role(mgr, forbidden))
        self.assertTrue(can_assign_role(own, "owner"))
        for role in ("supervisor", "worker", "advisor", "viewer"):
            self.assertFalse(can_assign_role(Membership(role), "viewer"))
        self.assertFalse(can_assign_role(Membership("manager", frozenset({1})), "worker"))
        self.assertFalse(can_assign_role(None, "viewer"))

    def test_member_changes(self):
        mgr, own = Membership("manager"), Membership("owner")
        self.assertTrue(can_change_member(mgr, "worker", "viewer", owners=1))
        self.assertTrue(can_change_member(mgr, "worker", None, owners=1))
        self.assertFalse(can_change_member(mgr, "manager", "worker", owners=1), "managers cannot demote peers")
        self.assertFalse(can_change_member(mgr, "owner", None, owners=2), "managers cannot remove an owner")
        self.assertFalse(can_change_member(mgr, "worker", "manager", owners=1), "managers cannot promote to their own level")
        self.assertFalse(can_change_member(own, "owner", None, owners=1), "the last owner can never be removed")
        self.assertFalse(can_change_member(own, "owner", "viewer", owners=1), "the last owner can never be demoted")
        self.assertTrue(can_change_member(own, "owner", "manager", owners=2))
        self.assertFalse(can_change_member(Membership("worker"), "viewer", None, owners=1))

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            Membership("god")


class ReportTests(unittest.TestCase):
    META = SensorMeta("t", "Barn 1 temperature", "C", 60, high_limit=30.0)

    def test_days_are_local_and_dst_days_are_not_24_hours(self):
        s, e = local_day_bounds(date(2026, 11, 10), "Africa/Lagos")
        self.assertEqual((e - s), timedelta(hours=24))
        self.assertEqual(s, datetime(2026, 11, 9, 23, 0, tzinfo=UTC))
        s, e = local_day_bounds(date(2026, 3, 8), "America/New_York")
        self.assertEqual((e - s), timedelta(hours=23))
        s, e = local_day_bounds(date(2026, 11, 1), "America/New_York")
        self.assertEqual((e - s), timedelta(hours=25))
        s, e = local_day_bounds(date(2026, 10, 25), "Europe/Berlin")
        self.assertEqual((e - s), timedelta(hours=25))

    def make(self):
        start, end = local_day_bounds(date(2026, 11, 10), "Africa/Lagos")
        pts = simulate_temperature(start, end, 60, seed=3, mean=27, amplitude=4)
        return build_daily_report("Green Acres", date(2026, 11, 10), "Africa/Lagos", [self.META], {"t": pts},
                                  [{"severity": "warning"}, {"severity": "critical"}, {"severity": "warning"}]), pts

    def test_summary_numbers_match_the_data(self):
        report, pts = self.make()
        s = report.sensors[0]
        values = [v for _, v in pts]
        self.assertEqual((s.count, s.expected, s.uptime_pct), (1440, 1440, 100.0))
        self.assertEqual((s.minimum, s.maximum), (min(values), max(values)))
        self.assertAlmostEqual(s.average, sum(values) / len(values))
        self.assertEqual(s.minutes_above_limit, sum(v > 30 for v in values))
        self.assertEqual(report.alerts_by_severity, {"warning": 2, "critical": 1})

    def test_readings_outside_the_local_day_are_ignored(self):
        start, end = local_day_bounds(date(2026, 11, 10), "Africa/Lagos")
        pts = [(start - timedelta(minutes=1), 99.0), (start, 20.0), (end - timedelta(minutes=1), 22.0), (end, 99.0)]
        s = build_daily_report("F", date(2026, 11, 10), "Africa/Lagos", [self.META], {"t": pts}).sensors[0]
        self.assertEqual((s.count, s.maximum), (2, 22.0))

    def test_a_dead_sensor_is_reported_loudly(self):
        report = build_daily_report("F", date(2026, 11, 10), "Africa/Lagos", [self.META], {})
        self.assertIn("NO DATA", render_text(report))

    def test_text_and_pdf_contain_the_facts(self):
        report, _ = self.make()
        text = render_text(report)
        self.assertIn("Green Acres", text)
        self.assertIn("Alerts: 1 critical, 2 warning.", text)
        pdf = render_pdf(report)
        self.assertTrue(pdf.startswith(b"%PDF"))
        extracted = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("Green Acres", extracted)
        self.assertIn("Barn 1 temperature", extracted)
        self.assertIn(f"{report.sensors[0].maximum:.1f}", extracted)

    def test_dst_day_expects_fewer_readings(self):
        start, end = local_day_bounds(date(2026, 3, 8), "America/New_York")
        pts = simulate_temperature(start, end, 60, seed=1)
        s = build_daily_report("F", date(2026, 3, 8), "America/New_York", [self.META], {"t": pts}).sensors[0]
        self.assertEqual((s.expected, s.count, s.uptime_pct), (1380, 1380, 100.0))


class InsightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start, end = local_day_bounds(date(2026, 11, 10), "Africa/Lagos")
        pts = simulate_temperature(start, end, 60, seed=5, mean=29, amplitude=5)
        cls.report = build_daily_report("Green Acres", date(2026, 11, 10), "Africa/Lagos",
                                        [SensorMeta("t", "Barn 1 temperature", "C", 60, high_limit=30.0)], {"t": pts}, [{"severity": "warning"}])
        cls.facts = facts_from_report(cls.report)

    def reply(self, **over):
        rec = {"title": "Improve ventilation in the afternoon", "action": "Open the side vents earlier and check the fans around 12:00.",
               "reason": f"Barn 1 temperature was above the limit of 30 C for {self.report.sensors[0].minutes_above_limit} minutes.",
               "urgency": "today", "confidence": "medium", "fact_ids": ["F2"]}
        rec.update(over)
        return json.dumps({"summary": "The barn ran hot in the afternoon.", "recommendations": [rec]})

    def test_facts_carry_ids_and_the_numbers_they_mention(self):
        self.assertEqual(self.facts[0].id, "F1")
        self.assertIn("Barn 1 temperature", self.facts[0].text)
        self.assertIn(self.report.sensors[0].maximum, self.facts[0].numbers)
        system, user = build_prompt(self.facts, "Poultry house, 5000 birds.")
        self.assertIn("[F1]", user)
        self.assertIn("Poultry house", user)
        self.assertIn("ONLY the facts", system)

    def test_a_good_reply_passes(self):
        ins = validate_insight(self.reply(), self.facts)
        self.assertEqual(len(ins.recommendations), 1)
        self.assertFalse(ins.recommendations[0].redacted)
        self.assertEqual(ins.dropped, [])

    def test_code_fences_are_tolerated(self):
        self.assertEqual(len(validate_insight("```json\n" + self.reply() + "\n```", self.facts).recommendations), 1)

    def test_an_invented_number_in_the_reason_drops_the_recommendation(self):
        ins = validate_insight(self.reply(reason="The temperature reached 47.5 C yesterday."), self.facts)
        self.assertEqual(ins.recommendations, [])
        self.assertIn("not in the facts", ins.dropped[0])

    def test_an_invented_number_in_the_summary_rejects_the_reply(self):
        bad = json.dumps({"summary": "It was 51.2 degrees in the barn.", "recommendations": []})
        with self.assertRaises(InvalidInsight):
            validate_insight(bad, self.facts)

    def test_unknown_fact_ids_and_missing_fields_are_dropped(self):
        self.assertEqual(validate_insight(self.reply(fact_ids=["F99"]), self.facts).recommendations, [])
        self.assertEqual(validate_insight(self.reply(fact_ids=[]), self.facts).recommendations, [])
        self.assertEqual(validate_insight(self.reply(urgency="whenever"), self.facts).recommendations, [])
        self.assertEqual(validate_insight(self.reply(action=""), self.facts).recommendations, [])

    def test_advice_may_contain_small_practical_numbers_but_not_invented_readings(self):
        self.assertEqual(len(validate_insight(self.reply(action="Check the fans every 30 minutes."), self.facts).recommendations), 1)
        self.assertEqual(validate_insight(self.reply(action="Cool the barn to 18.5 C."), self.facts).recommendations, [])

    def test_medical_and_safety_bypass_advice_is_replaced_by_a_referral(self):
        for risky in ("Give the flock an antibiotic in the water.", "Disable the alarm until the heat passes.", "Increase the dosage of electrolytes.",
                      "Spray pesticide on the litter."):
            rec = validate_insight(self.reply(action=risky), self.facts).recommendations[0]
            self.assertTrue(rec.redacted, risky)
            self.assertEqual(rec.action, SAFE_REFERRAL)

    def test_garbage_is_rejected_so_the_caller_can_fall_back(self):
        for raw in ("I think it was hot.", "[]", '{"summary": 5}', "", '{"summary": "x"}'):
            with self.assertRaises(InvalidInsight):
                validate_insight(raw, self.facts)

    def test_at_most_five_recommendations_and_fallback(self):
        many = json.dumps({"summary": "ok", "recommendations": [json.loads(self.reply())["recommendations"][0]] * 8})
        self.assertEqual(len(validate_insight(many, self.facts).recommendations), 5)
        fb = fallback_insight(self.facts)
        self.assertTrue(fb.fallback)
        self.assertEqual(fb.recommendations, [])


class PartitionTests(unittest.TestCase):
    def test_names_and_ddl(self):
        self.assertEqual(partitions.partition_name(date(2026, 11, 11)), "farmsense_reading_2026_11")
        self.assertEqual(partitions.partition_ddl(date(2026, 12, 20)),
                         "CREATE TABLE IF NOT EXISTS farmsense_reading_2026_12 PARTITION OF farmsense_reading "
                         "FOR VALUES FROM ('2026-12-01') TO ('2027-01-01')")

    def test_year_rollover(self):
        self.assertEqual(partitions.add_months(date(2026, 12, 1), 1), date(2027, 1, 1))
        self.assertEqual(partitions.add_months(date(2026, 1, 1), -2), date(2025, 11, 1))
        ddl = partitions.partitions_to_create(date(2026, 11, 30), ahead=2)
        self.assertEqual([d.split(" ")[5] for d in ddl], ["farmsense_reading_2026_11", "farmsense_reading_2026_12", "farmsense_reading_2027_01"])

    def test_retention_drops_only_whole_old_months_and_only_our_tables(self):
        existing = ["farmsense_reading_2025_09", "farmsense_reading_2025_10", "farmsense_reading_2025_11", "farmsense_reading_2026_11",
                    "farmsense_reading_default", "users", "farmsense_reading_2025_1x"]
        self.assertEqual(partitions.partitions_to_drop(existing, date(2026, 11, 11), keep_months=12), ["farmsense_reading_2025_09", "farmsense_reading_2025_10"])
        self.assertEqual(partitions.partitions_to_drop(existing, date(2026, 11, 11), keep_months=36), [])


class DeviceSimulatorScriptTests(unittest.TestCase):
    def test_the_fake_device_sends_payloads_the_server_logic_accepts(self):
        import importlib.util, os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "simulate_device.py")
        spec = importlib.util.spec_from_file_location("simulate_device", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
        batches = mod.build_batches("barn1-temp", now, minutes=500, heat=True, batch_size=200)
        self.assertEqual([len(b["readings"]) for b in batches], [200, 200, 100])
        total = 0
        for b in batches:
            result = parse_batch(b, {"barn1-temp": "temperature"}, now)
            self.assertEqual(result.rejected, [])
            total += len(result.accepted)
        self.assertEqual(total, 500)


class MiscTests(unittest.TestCase):
    def test_simulator_is_deterministic_and_shaped_like_a_day(self):
        a = simulate_temperature(T0, T0 + timedelta(days=1), 60, seed=1)
        self.assertEqual(a, simulate_temperature(T0, T0 + timedelta(days=1), 60, seed=1))
        self.assertNotEqual(a, simulate_temperature(T0, T0 + timedelta(days=1), 60, seed=2))
        by_hour = {}
        for ts, v in a:
            by_hour.setdefault(ts.hour, []).append(v)
        self.assertGreater(sum(by_hour[15]) / len(by_hour[15]), sum(by_hour[4]) / len(by_hour[4]) + 5)

    def test_capacity(self):
        c = capacity.estimate(sensors=200, interval_s=60)
        self.assertEqual(c["rows_per_day"], 288_000)
        self.assertEqual(c["rows_per_year"], 105_120_000)
        self.assertAlmostEqual(c["writes_per_second"], 3.33, places=2)
        self.assertGreater(c["gb_per_year"], 10)


if __name__ == "__main__":
    unittest.main()
