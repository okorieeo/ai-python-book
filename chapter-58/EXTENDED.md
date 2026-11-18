# Chapter 58 — Project 3: Smart Farm / IoT Monitoring App with AI Insights: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Architecture and Decisions › The shape of the data

| **Model** | **Holds** | **Detail worth knowing** |
|---|---|---|
| **Farm, Site** | A business and its barns, greenhouses and fields | The farm has a **time zone**: reports are cut at its midnight |
| **Membership** | A user’s role on a farm, and which sites | An explicit **all_sites** flag, not "an empty list means everything" |
| **Device, Sensor** | A box with a key, and the measurements it reports | Only the **hash** of the key is stored |
| **Reading** | One value at one time | Not an ORM model: a partitioned SQL table written in bulk |
| **AlertRule, AlertState, Alert** | The limits, the engine’s memory, and the history people read | State is saved after every tick |
| **PushToken** | A phone that can receive alerts | A token moves with the phone, not the person |
| **DailyReport, DailyInsight** | The finished products for a farm and a day | A **unique (farm, day)** constraint makes the tasks safe to run twice |

> **Why "all_sites" is a boolean**
>
> A common design says: "a membership with no sites is allowed everywhere". Then someone deletes the last site of a restricted worker, and that worker silently becomes a farm-wide user. An explicit all_sites flag means a restricted membership with no sites sees **nothing**, which fails safe.


## Project Setup

The code has the same split as Chapter 57, and for the same reason:

| **Folder** | **Contains** | **Tested here?** |
|---|---|---|
| farmsense_core | Sensor rules, batch validation, device keys, aggregation, alert engine, permissions, reports, AI guardrails, partitions, simulator | **Yes: 65 tests** |
| farmsense | The Django app: models, ingest endpoint, tasks, consumer, views, push | Syntax-checked only |
| frontend, mobile | Next.js and Expo components | Syntax-checked only |
| scripts | A fake device that sends simulated readings to your server | Its payloads are tested |

Everything that decides whether a reading is believable, when a person is woken, who may see what, and whether an AI reply is safe, is **plain Python**. You can run its tests in a fraction of a second, which is what lets you change an alert rule with confidence.

**bash terminal**

```bash
unzip Chapter_58_code.zip && cd chapter_58_code
pip install pypdf reportlab
python3 -m unittest discover -s tests -t . -v
python3 -m farmsense_core.replay
```


## Roles and Permissions › One function, four places

| **Where** | **How it asks** |
|---|---|
| REST views | can(membership, "alert.ack", site_id) before acting |
| The live WebSocket | Checked at connection **and again for every message**, because a person may be demoted while connected |
| Celery notifications | Chooses recipients with can(membership, "alert.view", site_id), so a worker is never pushed another site’s alerts |
| The apps | Hide buttons by asking the API what the person may do, but the **server** is what enforces |

Two habits make this robust. First, an object you may not see looks exactly like one that does not exist (404, not 403), so ids cannot be probed. Second, the matrix is tested **exhaustively**: the test walks every role and every action, and asserts that a site-limited member can never do a farm-wide action and never touches another site. When you add a new action, the test forces you to decide where it belongs.


## Devices and Ingestion › Hardware lies, so every reading is checked

| **Rule** | **Why** |
|---|---|
| The sensor must belong to **this** device | A stolen or confused key cannot write to another farm’s sensors |
| Timestamps need a **time zone** (ISO 8601) or are Unix seconds or milliseconds | A time without a zone is ambiguous, and ambiguity becomes a wrong chart at midnight |
| Not more than 5 minutes in the future, not older than 7 days | A device with a wrong clock would otherwise write into the future and confuse every alert |
| Values must be real numbers inside the **physical range** of the sensor type | A loose cable reads minus 127 or 85 degrees: that is a fault, not a measurement |
| Convert known units, refuse unknown ones | "furlongs" is not a unit |
| No duplicates inside one batch, at most 500 readings per request | Protects the database and the request size |

The result is not "accepted" or "rejected" for the whole batch. Each reading is judged separately, and the response says exactly what happened, so a device (or the person debugging it) can see why:

**text verified: one batch with mixed quality (from the tests)**

```text
accepted 2, rejected 6
reasons: unknown_sensor, bad_timestamp, in_future, too_old, out_of_range, duplicate_in_batch
```


## Storing Time-Series Data › Never chart raw points

A chart of a month of one-minute data would need 43,200 points per sensor, far more than a screen has pixels. The API returns **buckets**: the sensor’s time range is divided into about 300 buckets, and each carries the average, minimum and maximum, computed in SQL with date_bin. The range is capped (93 days), because an unbounded query is a way to take your server down.

**python farmsense/readings_sql.py (bucketed)**

```python
cur.execute(
    "SELECT date_bin(make_interval(secs => %s), ts, TIMESTAMPTZ '2000-01-01') AS bucket, count(*), avg(value), min(value), max(value) "
    "FROM farmsense_reading WHERE sensor_id = %s AND ts >= %s AND ts < %s GROUP BY bucket ORDER BY bucket",
    [bucket_seconds, sensor_id, start, end])
```

Always keep the **minimum and maximum** next to the average. An average hides the spike that cooked the flock, which is the only thing the farmer cares about.

For long ranges (a year of charts) add an **hourly rollup table** filled by a periodic task, so that yearly charts read 8,760 rows per sensor instead of 31 million.


## Alerts That People Trust › The states

1. **OK.** Nothing to report. When the condition becomes true, move to PENDING and remember **when** it started.
2. **PENDING.** If the condition goes away, forget it (OK again). If it has held for for_seconds, move to FIRING and **tell people**.
3. **FIRING.** Resolve only when the value passes the clear line. While firing and unacknowledged, send a **reminder** every cooldown, and **one escalation** after the escalation delay. When a person **acknowledges**, reminders and escalation stop, but the alert stays open until the problem is really over.
The **no data** rule is special: its "condition" is silence. A sensor that stops reporting is a problem of its own (a dead battery, a cut cable), and a silent system must not look like a healthy one. Its for_seconds is the silence allowed, and it is quiet until the sensor has reported at least once.

The engine takes the time as an argument and never reads the clock, so tests can replay hours in microseconds and always get the same answer. The tests cover: a short spike never fires, a sustained breach fires once after the wait, hysteresis, reminders with their cooldown, acknowledgement, escalation exactly once, firing again after resolution, the below rule, the rate rule, silence and recovery, and a missed tick not resolving a firing alert.


## Alerts That People Trust › Watch it work

The replay script runs a deterministic three-day simulation through the rules. Day 1 has two one-reading glitches (a loose cable), day 2 has a heat wave in the afternoon, day 3 has a 40-minute sensor dropout and one more glitch. Someone acknowledges the heat-wave alert at 14:20. A fourth, **naive** rule is included for comparison: alert the moment the value passes 30, no waiting, no hysteresis, remind every minute.

*(figure: see the printed book)*

**text verified output: python3 -m farmsense_core.replay**

```text
4280 readings over 3 days; one every minute; spikes on day 1 and 3, heat wave on day 2, dropout on day 3

rule                                               fire  remind  escal.  resolve  messages
High temperature                                      1       2       0        1         4
Critical temperature                                  1       1       1        1         4
Sensor offline                                        1       0       0        1         2
Naive (no wait, no hysteresis, 1-min reminders)      11     359       0       11       381

Timeline of the real rules (UTC):
  day 2 13:06  fire     High temperature value 30.9
  day 2 13:36  reminder High temperature value 32.9
  day 2 13:48  fire     Critical temperature value 33.2
  day 2 14:03  escalate Critical temperature value 34.3
  day 2 14:06  reminder High temperature value 34.2
  day 2 14:18  reminder Critical temperature value 34.7
  day 2 18:38  resolve  Critical temperature value 31.4
  day 2 19:14  resolve  High temperature value 29.0
  day 3 02:14  fire     Sensor offline
  day 3 02:40  resolve  Sensor offline value 20.7

Heat wave: temperature first above 30 at day 2 12:47.
  warning fired after 19 min, critical after 61 min.
  glitches that triggered a real alert: 0 of 3.   The naive rule fired 11 times.
```

Read the numbers, because they teach the trade-offs:

- The real rules sent **10 messages in three days**. The naive rule sent **381**. Nobody reads 381 messages; everybody reads 10.
- All **three glitches caused no alert**, and the naive rule fired on every wobble above 30, eleven times in total.
- The heat wave was noticed **19 minutes** after the temperature first crossed 30, not instantly. That delay is the **price** of not crying wolf (10 minutes of waiting, plus smoothing, plus noise near the line). If 19 minutes is too slow for your animals, shorten for_seconds or lower the threshold, and accept more false alarms. This is a real decision, and now you can **measure** it instead of guessing.
- The critical alert escalated at 14:03 because nobody had acknowledged. The acknowledgement at 14:20 stopped further reminders.
- The dropout was noticed after 15 minutes of silence, and the alert resolved by itself when readings returned.

## Alerts That People Trust › Running the engine in production

The engine is pure, so production needs a thin loop around it: every minute a Celery task loads each enabled rule, takes the newest reading of its sensor, **restores the rule’s saved state**, calls step(), **saves the state** and sends notifications for any events. Three details keep it correct:

- **State is saved in the database** (AlertState), because the next tick may run on another worker or after a restart.
- Rows are locked with SELECT ... FOR UPDATE SKIP LOCKED, so that if one tick is slow, the next does not process the same rule twice.
- A rule only sees a reading as "new" if it is newer than the last one it processed. Otherwise a stuck sensor would be evaluated as if it kept reporting.
Give alerts **their own queue and worker**. A slow PDF report must never delay a fire alarm.


## Real-Time Dashboards › Keep the browser honest

| **Problem** | **What the interface does** |
|---|---|
| A sensor stopped reporting | After three missed intervals the tile greys out and says **No recent data**. An old number must never look live |
| The connection dropped | Reconnect with exponential backoff **and jitter** (a random wait), so that a server restart does not make thousands of dashboards reconnect in the same second |
| The page was open all night | The buffer is capped at 120 points, so memory never grows |
| Colour-blind users | Status is written in words as well as colour ("Too high"), and the chart has a text label |
| The user missed updates while disconnected | On reconnect, fetch the last few minutes from the bucketed REST endpoint to fill the gap, then continue live |

**typescript frontend/SensorTile.tsx (staleness)**

```typescript
if (now - last.ts > s.interval_s * 3 * 1000) return "stale";   // no reading for three intervals: do not show an old number as if it were live
```


## Notifications and Mobile Alerts › Things that trip everyone up

| **Trap** | **What to know** |
|---|---|
| Testing on a simulator | Push notifications need a **physical device** |
| Expo Go | Recent Expo versions do not support push notifications in Expo Go. You need a **development build** (Chapter 26) |
| Android permission | Android 13 and later ask for the notification permission, and it only appears **after a notification channel exists**, so create the channel first |
| The project id | getExpoPushTokenAsync needs your EAS project id (run eas init). Without it, token registration fails |
| Credentials | Android needs Firebase (FCM) credentials and iOS needs an Apple push key, uploaded through EAS. Without them a token is issued but nothing arrives |
| Delivery is not guaranteed | Phones in power saving, no network, or Do Not Disturb delay or drop pushes. Treat push as **best effort** and keep a second channel for critical alerts |
| Rate | Expo allows a high rate per project (hundreds of messages a second), more than a farm will ever need |


## Scheduled Reports › Things reports must get right

| **Detail** | **Why** |
|---|---|
| A sensor with **no data** is printed as "NO DATA", never as zero or left out | A silent sensor is the most important line of the report |
| Late-arriving readings | A report is built from stored data at 01:00 local time. Data that arrives later is in the database but not in that PDF. Say so in the footer, or rebuild reports on request |
| The same numbers as the dashboard | Both use the same functions and the same stored readings, so the owner never sees two different maxima |
| Storage | PDFs go to **private** storage and are served through the API with permission checks (report.view), not as public URLs |
| E-mail | Only owners and managers, and the e-mail body repeats the key numbers in text, since many people read on a phone and never open attachments |


## Testing the Platform

You cannot test a farm by waiting for it to overheat, so the project is built to be tested **without one**.

| **Layer** | **How it is tested** | **Where** |
|---|---|---|
| Reading and batch validation | Table-driven tests with deliberately bad input | farmsense_core tests |
| Device keys | Round trip, wrong secrets, revocation, tampering, replay | farmsense_core tests |
| Alert engine | Scripted series: spike, sustained breach, wobble, reminders, acknowledgement, escalation, silence | farmsense_core tests |
| **Scenarios** | The three-day replay with assertions on what a good rule set must do | replay tests |
| Permissions | **Exhaustive** loop over every role and every action, plus escalation attempts | farmsense_core tests |
| Reports | Day boundaries including daylight saving, exact numbers, a real PDF read back | farmsense_core tests |
| AI guardrails | Every validator rule with a good reply and a bad reply | farmsense_core tests |
| Partitions | Rollover, retention, and "never drop what is not ours" | farmsense_core tests |
| Tenant isolation | Real database, two farms, an attacker’s requests | farmsense/test_tenant_isolation.py |
| The device payloads | The fake device’s JSON is accepted by the real validation | farmsense_core tests |

Two practices are worth copying. First, the **simulator is deterministic** (the same seed gives the same data), so a failing test always fails the same way, and the book’s examples never change. Second, **scenario tests state the product’s promise in numbers**: "the heat wave is detected within 30 minutes, the glitches cause no alert, the naive rule sends more than twenty times as many messages". When you tune a rule, the scenario tells you immediately what you gained and what you lost.

**text verified: the test run**

```text
Ran 65 tests in 0.2s
OK
```


## Deploying FarmSense

Follow Chapters 53 and 54, with these differences.

| **Topic** | **What changes** |
|---|---|
| **Processes** | Four: the web and WebSocket server, a worker for the **alerts** queue, a worker for everything else (reports, insights, maintenance), and **one** Celery Beat. Never scale Beat |
| **Ingest traffic** | Devices post every minute around the clock. Put the ingest endpoint behind rate limiting, and size the web workers for steady load, not for peaks of human browsing |
| **Partitions** | Run the partition task right after the first deploy, and check that next month’s partition exists before the 1st. A missing partition falls into the default one, which works but defeats the point |
| **The database** | Back it up (Chapter 54) and **restore it in the drill**. Plan disk for about 14 GB a year per 200 sensors with indexes, and keep an eye on it |
| **Time** | The server and database in UTC, the farms’ zones in the database. Check that the clock is synchronised (Chapter 53): wrong server time becomes wrong alerts |
| **Secrets** | Anthropic key, Expo access token (if you enabled enhanced push security), e-mail credentials, in the Environment tab |
| **Mobile** | Push needs Firebase and Apple credentials uploaded through EAS, and a development or production build, not Expo Go |


### Who watches the watcher?

The scariest failure is the quiet one: the alert worker crashes, nothing evaluates, nothing fires, and the dashboard looks fine because it only shows the last reading. So the alert system needs a **dead-man’s switch**: something outside it that expects a signal and complains when the signal stops.

- At the end of every successful evaluation tick, the task pings an external **heartbeat monitor** (a URL that raises an alarm if it is not called for five minutes).
- The readiness check (Chapter 54) also verifies that the timestamp of the last successful tick is recent.
- Monitor the **queue length** and the age of the oldest queued alert task (Chapter 55).
- Test the whole chain on purpose: stop the worker, and confirm that you receive the "alerts are not being evaluated" message on your own phone.
Tell the farm too: if **no data** arrives from the gateway for 30 minutes, the **platform** raises it, which is exactly the no-data rule from 58.4 applied to the gateway.
