"""Celery tasks: alert evaluation, notifications, partitions, reports and AI insights. NOT executed in the book's test environment.

Schedule (settings.CELERY_BEAT_SCHEDULE), every task is safe to run twice:
  evaluate_rules       every 60 s
  ensure_partitions    daily
  drop_old_partitions  weekly
  daily_reports        hourly   (each farm gets its report in its own first hours after local midnight)"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import connection, transaction

from farmsense_core import alerts as engine
from farmsense_core.sensors import SENSOR_TYPES
from farmsense_core.insights import InvalidInsight, build_prompt, facts_from_report, fallback_insight, validate_insight
from farmsense_core.partitions import partitions_to_create, partitions_to_drop
from farmsense_core.permissions import can
from farmsense_core.reports import SensorMeta, build_daily_report, local_day_bounds, render_pdf, render_text

from .models import Alert, AlertRule, AlertState, DailyInsight, DailyReport, Farm, Membership, PushToken, Sensor
from .push import send_push
from .readings_sql import latest

log = logging.getLogger(__name__)


def _to_evaluator(rule: AlertRule, st: AlertState) -> engine.Evaluator:
    r = engine.Rule(rule.name, rule.kind, rule.threshold, rule.for_seconds, rule.clear_threshold, rule.severity,
                    rule.cooldown_seconds, rule.escalate_after_seconds)
    prev = (st.prev_ts, st.prev_value) if st.prev_ts else None
    return engine.Evaluator(r, st.state, st.since, st.fired_at, st.last_notified, st.escalated, st.acknowledged, st.last_seen, prev)


def _save(st: AlertState, ev: engine.Evaluator) -> None:
    st.state, st.since, st.fired_at, st.last_notified = ev.state, ev.since, ev.fired_at, ev.last_notified
    st.escalated, st.acknowledged, st.last_seen = ev.escalated, ev.acknowledged, ev.last_seen
    st.prev_ts, st.prev_value = (ev.prev if ev.prev else (None, None))
    st.save()


@shared_task
def evaluate_rules() -> int:
    """One tick: look at the newest reading of every sensor that has an enabled rule and step each rule's state machine."""
    now = datetime.now(timezone.utc)
    rules = list(AlertRule.objects.filter(enabled=True).select_related("sensor", "sensor__site__farm"))
    newest = latest([r.sensor_id for r in rules])
    fired = 0
    for rule in rules:
        with transaction.atomic():
            # skip_locked: if the previous tick is still working on this rule, do not wait and do not double-process it
            AlertState.objects.get_or_create(rule=rule)
            st = AlertState.objects.select_for_update(skip_locked=True).filter(rule=rule).first()
            if st is None:
                continue
            ev = _to_evaluator(rule, st)
            ts, value = newest.get(rule.sensor_id, (None, None))
            fresh = ts is not None and (st.prev_ts is None or ts > st.prev_ts)
            for event in ev.step(now, value if fresh else None):
                fired += 1
                _record(rule, event)
                transaction.on_commit(lambda e=event, r=rule: notify.delay(r.id, e.kind, e.severity, e.value))
            _save(st, ev)
    return fired


def _record(rule: AlertRule, event: engine.Event) -> None:
    if event.kind == "fire":
        Alert.objects.create(rule=rule, started_at=event.at, peak_value=event.value)
    elif event.kind == "resolve":
        Alert.objects.filter(rule=rule, resolved_at__isnull=True).update(resolved_at=event.at)


@shared_task
def notify(rule_id: int, kind: str, severity: str, value) -> None:
    rule = AlertRule.objects.select_related("sensor__site__farm").get(pk=rule_id)
    farm, site = rule.sensor.site.farm, rule.sensor.site
    recipients = [m for m in Membership.objects.filter(farm=farm).select_related("user")
                  if can(m.to_core(), "alert.view", site.id)
                  and (kind != "escalate" or m.role in ("owner", "manager"))]        # escalation wakes up the people above the shift
    title = f"{severity.upper()}: {rule.name} at {site.name}" if kind != "resolve" else f"Resolved: {rule.name} at {site.name}"
    body = f"{rule.sensor.name}: {value}" if value is not None else rule.sensor.name
    tokens = list(PushToken.objects.filter(user__in=[m.user for m in recipients]).values_list("token", flat=True))
    try:
        dead = send_push(tokens, title, body, {"alert_rule": rule.id, "kind": kind}, critical=(severity == "critical"))
        PushToken.objects.filter(token__in=dead).delete()
    except Exception:
        # push failed: a critical alert must still reach people, so fall back to e-mail
        EmailMessage(title, body, to=[m.user.email for m in recipients if m.user.email]).send(fail_silently=True)


@shared_task
def ensure_partitions() -> None:
    with connection.cursor() as cur:
        for ddl in partitions_to_create(datetime.now(timezone.utc).date(), ahead=2):
            cur.execute(ddl)


@shared_task
def drop_old_partitions(keep_months: int = 13) -> list:
    with connection.cursor() as cur:
        cur.execute("SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                    "JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = 'farmsense_reading'")
        names = [r[0] for r in cur.fetchall()]
        doomed = partitions_to_drop(names, datetime.now(timezone.utc).date(), keep_months)
        for name in doomed:
            cur.execute(f'DROP TABLE IF EXISTS "{name}"')       # names come from partitions_to_drop, which only returns our own pattern
    return doomed


def _report_for(farm: Farm, day):
    start, end = local_day_bounds(day, farm.timezone)
    sensors = list(Sensor.objects.filter(site__farm=farm))
    readings = {}
    with connection.cursor() as cur:
        for s in sensors:
            cur.execute("SELECT ts, value FROM farmsense_reading WHERE sensor_id = %s AND ts >= %s AND ts < %s ORDER BY ts", [s.id, start, end])
            readings[s.key] = cur.fetchall()
    metas = [SensorMeta(s.key, s.name, SENSOR_TYPES[s.type].unit, s.interval_s, s.high_limit, s.low_limit) for s in sensors]
    alerts = [{"severity": a.rule.severity} for a in Alert.objects.filter(rule__sensor__site__farm=farm, started_at__gte=start, started_at__lt=end).select_related("rule")]
    return build_daily_report(farm.name, day, farm.timezone, metas, readings, alerts)


@shared_task
def daily_reports() -> int:
    """Hourly. A farm's report for 'yesterday' is created in the first hours after ITS local midnight, exactly once
    (the unique constraint makes a second run harmless)."""
    made = 0
    for farm in Farm.objects.all():
        local_now = datetime.now(ZoneInfo(farm.timezone))
        if local_now.hour >= 6:
            continue
        day = local_now.date() - timedelta(days=1)
        if DailyReport.objects.filter(farm=farm, day=day).exists():
            continue
        report = _report_for(farm, day)
        obj = DailyReport(farm=farm, day=day)
        obj.pdf.save(f"{farm.id}-{day}.pdf", ContentFile(render_pdf(report)), save=False)
        try:
            with transaction.atomic():
                obj.save()
        except Exception:
            continue                                            # another worker won the race
        made += 1
        owners = [m.user.email for m in Membership.objects.filter(farm=farm, role__in=("owner", "manager")).select_related("user") if m.user.email]
        mail = EmailMessage(f"{farm.name}: daily report for {day}", render_text(report), to=owners)
        mail.attach(f"report-{day}.pdf", render_pdf(report), "application/pdf")
        mail.send(fail_silently=True)
        generate_insight.delay(farm.id, day.isoformat())
    return made


@shared_task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3)
def generate_insight(self, farm_id: int, day_iso: str) -> None:
    """Facts from code, words from the model, checks from code. If anything is off, the day still gets a plain-facts insight."""
    import anthropic
    from datetime import date
    from django.conf import settings
    farm, day = Farm.objects.get(pk=farm_id), date.fromisoformat(day_iso)
    facts = facts_from_report(_report_for(farm, day))
    system, user = build_prompt(facts, f"Farm: {farm.name}.")
    model = getattr(settings, "INSIGHT_MODEL", "claude-sonnet-5-5")
    try:
        resp = anthropic.Anthropic(timeout=60.0, max_retries=2).messages.create(
            model=model, max_tokens=1200, system=system, messages=[{"role": "user", "content": user}])
        insight = validate_insight("".join(b.text for b in resp.content if b.type == "text"), facts)
        if insight.dropped:
            log.warning("insight for farm %s dropped recommendations: %s", farm_id, insight.dropped)
    except (InvalidInsight, anthropic.APIError):
        log.exception("insight for farm %s failed validation or the API call failed; using the fallback", farm_id)
        insight, model = fallback_insight(facts), ""
    DailyInsight.objects.update_or_create(farm=farm, day=day, defaults={
        "facts": [f.__dict__ for f in facts], "summary": insight.summary, "model": model, "fallback": insight.fallback,
        "recommendations": [r.__dict__ for r in insight.recommendations]})
