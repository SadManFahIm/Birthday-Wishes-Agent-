"""
predictive_birthday.py

Birthday unknown  - LinkedIn posts, profile info,  past activity 
approximate birthday guess  Result SQLite- save   scheduled
wishing- use 

Tables:
  predicted_birthdays - contact per row, predicted date + confidence + evidence
"""

import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

from browser_use import Agent, Browser
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

DB_FILE = Path("agent_history.db")


# ---------------------------------------------
# 1. DB SETUP
# ---------------------------------------------

def init_predicted_birthday_table():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predicted_birthdays (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                contact             TEXT    NOT NULL UNIQUE,
                profile_url         TEXT,
                predicted_month     INTEGER,
                predicted_day       INTEGER,
                predicted_year      INTEGER,
                confidence          TEXT    CHECK(confidence IN ('high','medium','low')),
                confidence_score    REAL,
                evidence            TEXT,
                prediction_method   TEXT,
                wish_sent           INTEGER DEFAULT 0,
                created_at          TEXT    NOT NULL,
                updated_at          TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("  predicted_birthdays table ready.")


def save_predicted_birthday(
    contact: str,
    profile_url: str,
    predicted_month: int | None,
    predicted_day: int | None,
    predicted_year: int | None,
    confidence: str,
    confidence_score: float,
    evidence: list[str],
    prediction_method: str,
):
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO predicted_birthdays
                (contact, profile_url, predicted_month, predicted_day,
                 predicted_year, confidence, confidence_score, evidence,
                 prediction_method, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                profile_url       = excluded.profile_url,
                predicted_month   = excluded.predicted_month,
                predicted_day     = excluded.predicted_day,
                predicted_year    = excluded.predicted_year,
                confidence        = excluded.confidence,
                confidence_score  = excluded.confidence_score,
                evidence          = excluded.evidence,
                prediction_method = excluded.prediction_method,
                updated_at        = excluded.updated_at
        """, (
            contact, profile_url, predicted_month, predicted_day,
            predicted_year, confidence, confidence_score,
            json.dumps(evidence, ensure_ascii=False),
            prediction_method, now, now,
        ))
        conn.commit()
    logger.info(" Predicted birthday saved: %s -> %s/%s (confidence: %s)",
                contact, predicted_month, predicted_day, confidence)


def get_predicted_birthday(contact: str) -> dict | None:
    if not DB_FILE.exists():
        return None
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT * FROM predicted_birthdays WHERE LOWER(contact) = LOWER(?)",
            (contact,)
        ).fetchone()
    if not row:
        return None
    cols = [
        "id", "contact", "profile_url", "predicted_month", "predicted_day",
        "predicted_year", "confidence", "confidence_score", "evidence",
        "prediction_method", "wish_sent", "created_at", "updated_at",
    ]
    data = dict(zip(cols, row))
    data["evidence"] = json.loads(data["evidence"] or "[]")
    return data


def get_all_predicted_birthdays() -> list[dict]:
    if not DB_FILE.exists():
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT * FROM predicted_birthdays ORDER BY predicted_month, predicted_day"
        ).fetchall()
    cols = [
        "id", "contact", "profile_url", "predicted_month", "predicted_day",
        "predicted_year", "confidence", "confidence_score", "evidence",
        "prediction_method", "wish_sent", "created_at", "updated_at",
    ]
    result = []
    for row in rows:
        data = dict(zip(cols, row))
        data["evidence"] = json.loads(data["evidence"] or "[]")
        result.append(data)
    return result


def get_todays_predicted_birthdays() -> list[dict]:
    """ predicted birthday  wish  """
    today = date.today()
    all_predictions = get_all_predicted_birthdays()
    due = []
    for p in all_predictions:
        if (
            p.get("predicted_month") == today.month
            and p.get("predicted_day") == today.day
            and not p.get("wish_sent")
            and p.get("confidence") in ("high", "medium")
        ):
            due.append(p)
    return due


def mark_predicted_wish_sent(contact: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE predicted_birthdays SET wish_sent = 1 WHERE LOWER(contact) = LOWER(?)",
            (contact,)
        )
        conn.commit()


# ---------------------------------------------
# 2. BROWSER TASK BUILDERS
# ---------------------------------------------

def build_profile_data_scrape_task(
    contact_name: str,
    profile_url: str,
    already_logged_in: bool,
    username: str,
    password: str,
) -> str:
    login_block = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in else
        f"Go to https://linkedin.com and log in:\n"
        f"  Email: {username}\n  Password: {password}\n"
        "Handle MFA if prompted.\n"
    )
    return f"""
Open the browser. {login_block}

GOAL: Collect as much data as possible about '{contact_name}' from LinkedIn
to help predict their birthday.

Profile URL: {profile_url}

STEP 1 - Open the profile page.
STEP 2 - Collect ALL of the following (leave null if not found):
  - Full name
  - Current job title and company
  - Education history (universities, graduation years)
  - Work experience (start dates, end dates)
  - LinkedIn "joined" date if visible
  - Any age mentions in About section
  - Location / timezone

STEP 3 - Go to their Activity/Posts section.
  - Collect up to 15 recent posts (text only, first 300 chars each)
  - Look specifically for:
      * Posts mentioning "my birthday", "turning [age]", "another year older",
        "celebrating today", "birthday month", anniversary posts
      * Posts from previous years mentioning birthday celebrations
      * Comments from others wishing them happy birthday (check post comments)
      * Any date-specific celebrations or "one year ago" LinkedIn memories

STEP 4 - Check their "Featured" section for birthday-related content.

OUTPUT FORMAT - respond ONLY with this JSON (no markdown):
{{
  "contact": "{contact_name}",
  "profile_url": "{profile_url}",
  "education": [
    {{"institution": "...", "degree": "...", "start_year": null, "end_year": null}}
  ],
  "work_experience": [
    {{"company": "...", "role": "...", "start": "...", "end": "..."}}
  ],
  "linkedin_joined": null,
  "about_text": null,
  "birthday_posts": [
    {{"text": "...", "date": "...", "type": "self_post|comment|memory"}}
  ],
  "age_mentions": [],
  "other_signals": []
}}
"""


def build_birthday_prediction_task(contact_name: str, profile_data_json: str) -> str:
    return f"""
You are an expert analyst specializing in inferring personal information
from public social media data.

Analyze the LinkedIn data below for '{contact_name}' and predict their birthday.

PROFILE DATA:
{profile_data_json}

PREDICTION STRATEGIES (use ALL that apply):

1. DIRECT MENTION - Did they post "Happy Birthday to me", "Turning 30 today",
   or similar? Extract exact date.

2. BIRTHDAY WISHES FROM OTHERS - Did others comment "Happy Birthday [name]"
   on a specific post? Extract the post date as the birthday.

3. LINKEDIN ANNIVERSARY MEMORY - LinkedIn sometimes shows "X years ago today"
   posts. If a birthday post appears as a memory, the original date is the birthday.

4. EDUCATION + AGE CALCULATION - If graduation year is known (e.g., 2015 for
   Bachelor's), typical age at graduation is 21-23. Subtract to estimate birth year.
   Month/day remain unknown -> set to null.

5. CAREER START - First job start year often indicates age 22-24 after graduation.

6. DIRECT AGE MENTION - "I'm turning 28 this year" + current year -> birth year.

7. SEASONAL HINTS - "Winter baby", "born in summer", "Sagittarius", "Leo",
   "scorpio" -> approximate month range.

CONFIDENCE LEVELS:
- "high"   (score 0.75-1.0): Exact date found in posts/comments
- "medium" (score 0.40-0.74): Month known, day uncertain OR strong indirect signal
- "low"    (score 0.10-0.39): Only birth year estimated, or very weak signal

RESPOND ONLY with valid JSON (no markdown, no extra text):
{{
  "predicted_month": null,
  "predicted_day": null,
  "predicted_year": null,
  "confidence": "low",
  "confidence_score": 0.0,
  "evidence": [
    "Found post from 2023-03-15 where 3 people commented Happy Birthday",
    "Education shows graduation 2018, estimating birth year ~1996"
  ],
  "prediction_method": "birthday_wishes_from_others"
}}

If NO signal found at all:
{{
  "predicted_month": null,
  "predicted_day": null,
  "predicted_year": null,
  "confidence": "low",
  "confidence_score": 0.0,
  "evidence": ["No birthday signals found in available data"],
  "prediction_method": "no_signal"
}}
"""


def build_predicted_birthday_wish_task(
    contact_name: str,
    profile_url: str,
    prediction: dict,
    dry_run: bool,
    already_logged_in: bool,
    username: str,
    password: str,
) -> str:
    login_block = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in else
        f"Go to https://linkedin.com and log in:\n"
        f"  Email: {username}\n  Password: {password}\n"
    )
    dry = (
        "[DRY RUN] Do NOT send. Print: [DRY RUN] Would send to <name>: \"<message>\""
        if dry_run else
        "Send the message for real."
    )
    confidence  = prediction.get("confidence", "low")
    month       = prediction.get("predicted_month")
    day         = prediction.get("predicted_day")
    evidence    = "; ".join(prediction.get("evidence", []))

    # Confidence-based wish tone
    if confidence == "high":
        wish_note = "We are confident this is their birthday. Send a warm, direct birthday wish."
    elif confidence == "medium":
        wish_note = (
            "We think today might be their birthday based on patterns. "
            "Send a warm wish that gently acknowledges the uncertainty, e.g. "
            "'I have a feeling today might be your special day - if so, Happy Birthday!'"
        )
    else:
        wish_note = "Skip - confidence too low to wish."

    return f"""
Open the browser. {login_block}

TASK: Send a predicted birthday wish to {contact_name}.

Profile URL : {profile_url}
Confidence  : {confidence} (month={month}, day={day})
Evidence    : {evidence}

INSTRUCTION: {wish_note}

{dry}

After attempting, report: sent / skipped and reason.
"""


# ---------------------------------------------
# 3. CORE RUNNER
# ---------------------------------------------

async def predict_birthday_for_contact(
    contact_name: str,
    profile_url: str,
    llm: BaseChatModel,
    browser: Browser,
    already_logged_in: bool,
    username: str,
    password: str,
) -> dict | None:
    """
    One contact-  full prediction pipeline :
    scrape -> analyze -> save -> return prediction dict
    """
    logger.info(" Predicting birthday for: %s", contact_name)

    # -- Step 1: Scrape profile data --
    scrape_task = build_profile_data_scrape_task(
        contact_name, profile_url, already_logged_in, username, password
    )
    try:
        scrape_result = await Agent(task=scrape_task, llm=llm, browser=browser).run()
        raw = str(scrape_result)
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        profile_data = json.loads(raw[start:end]) if start != -1 else {}
    except Exception as e:
        logger.error(" Scrape failed for %s: %s", contact_name, e)
        return None

    # -- Step 2: Predict via LLM (no browser needed) --
    prediction_prompt = build_birthday_prediction_task(
        contact_name,
        json.dumps(profile_data, ensure_ascii=False, indent=2)
    )
    try:
        result = await llm.ainvoke(prediction_prompt)
        raw_pred = result.content if hasattr(result, "content") else str(result)
        start = raw_pred.find("{")
        end   = raw_pred.rfind("}") + 1
        prediction = json.loads(raw_pred[start:end])
    except Exception as e:
        logger.error(" Prediction LLM call failed for %s: %s", contact_name, e)
        return None

    # -- Step 3: Save --
    save_predicted_birthday(
        contact          = contact_name,
        profile_url      = profile_url,
        predicted_month  = prediction.get("predicted_month"),
        predicted_day    = prediction.get("predicted_day"),
        predicted_year   = prediction.get("predicted_year"),
        confidence       = prediction.get("confidence", "low"),
        confidence_score = prediction.get("confidence_score", 0.0),
        evidence         = prediction.get("evidence", []),
        prediction_method = prediction.get("prediction_method", "unknown"),
    )

    prediction["contact"]     = contact_name
    prediction["profile_url"] = profile_url
    return prediction


# ---------------------------------------------
# 4. BATCH RUNNER
# ---------------------------------------------

async def run_predictive_birthday(
    contacts: list[dict],          # [{"name": "...", "profile_url": "..."}]
    llm: BaseChatModel,
    browser: Browser,
    already_logged_in: bool,
    username: str,
    password: str,
    dry_run: bool = True,
    max_predictions: int = 20,
    min_confidence: str = "medium",  # "high" | "medium" | "low"
) -> list[dict]:
    """
    Batch prediction - contacts  birthday LinkedIn-  
    posts/profile  birthday guess 

    Returns list of prediction results.
    """
    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    min_rank = confidence_rank.get(min_confidence, 2)

    results = []
    processed = 0

    for c in contacts[:max_predictions]:
        name        = c.get("name", "")
        profile_url = c.get("profile_url", "")

        if not name or not profile_url:
            continue

        # Cached check -  already predicted?
        cached = get_predicted_birthday(name)
        if cached and cached.get("updated_at", "")[:10] == date.today().isoformat():
            logger.info(" Using cached prediction for %s", name)
            prediction = cached
        else:
            prediction = await predict_birthday_for_contact(
                contact_name      = name,
                profile_url       = profile_url,
                llm               = llm,
                browser           = browser,
                already_logged_in = already_logged_in or processed > 0,
                username          = username,
                password          = password,
            )

        if not prediction:
            continue

        conf = prediction.get("confidence", "low")
        conf_rank = confidence_rank.get(conf, 1)

        month = prediction.get("predicted_month")
        day   = prediction.get("predicted_day")

        #  birthday match   check 
        today = date.today()
        is_birthday_today = (
            month == today.month and day == today.day
            if (month and day) else False
        )

        entry = {
            "contact"         : name,
            "profile_url"     : profile_url,
            "predicted_month" : month,
            "predicted_day"   : day,
            "predicted_year"  : prediction.get("predicted_year"),
            "confidence"      : conf,
            "confidence_score": prediction.get("confidence_score", 0.0),
            "evidence"        : prediction.get("evidence", []),
            "method"          : prediction.get("prediction_method", "unknown"),
            "is_birthday_today": is_birthday_today,
        }
        results.append(entry)
        processed += 1

        logger.info(
            " %s -> %s/%s/%s | confidence: %s (%.2f) | method: %s | today: %s",
            name,
            month or "?", day or "?", prediction.get("predicted_year") or "?",
            conf,
            prediction.get("confidence_score", 0.0),
            prediction.get("prediction_method"),
            "" if is_birthday_today else "",
        )

        #  birthday   confidence threshold   wish 
        if is_birthday_today and conf_rank >= min_rank and not dry_run:
            wish_task = build_predicted_birthday_wish_task(
                contact_name      = name,
                profile_url       = profile_url,
                prediction        = prediction,
                dry_run           = dry_run,
                already_logged_in = True,
                username          = username,
                password          = password,
            )
            try:
                await Agent(task=wish_task, llm=llm, browser=browser).run()
                mark_predicted_wish_sent(name)
                logger.info(" Predicted birthday wish sent to %s!", name)
            except Exception as e:
                logger.error(" Wish sending failed for %s: %s", name, e)

        elif is_birthday_today and conf_rank >= min_rank and dry_run:
            logger.info("[DRY RUN] Would send predicted birthday wish to %s", name)

    logger.info(
        " Prediction done: %d/%d processed | today's birthdays: %d",
        processed,
        len(contacts),
        sum(1 for r in results if r["is_birthday_today"]),
    )
    return results


# ---------------------------------------------
# 5. DAILY WISH RUNNER (scheduled use)
# ---------------------------------------------

async def send_todays_predicted_wishes(
    llm: BaseChatModel,
    browser: Browser,
    already_logged_in: bool,
    username: str,
    password: str,
    dry_run: bool = True,
) -> list[str]:
    """
    DB   predicted birthdays   wish 
    daily_job()- call 
    """
    due = get_todays_predicted_birthdays()
    if not due:
        logger.info(" No predicted birthdays due today.")
        return []

    wished = []
    for p in due:
        wish_task = build_predicted_birthday_wish_task(
            contact_name      = p["contact"],
            profile_url       = p.get("profile_url", ""),
            prediction        = p,
            dry_run           = dry_run,
            already_logged_in = already_logged_in,
            username          = username,
            password          = password,
        )
        try:
            await Agent(task=wish_task, llm=llm, browser=browser).run()
            if not dry_run:
                mark_predicted_wish_sent(p["contact"])
            wished.append(p["contact"])
            logger.info(" Predicted wish sent to %s [conf: %s]",
                        p["contact"], p["confidence"])
        except Exception as e:
            logger.error(" Predicted wish failed for %s: %s", p["contact"], e)

    return wished


# ---------------------------------------------
# 6. DASHBOARD HELPERS
# ---------------------------------------------

def get_prediction_stats() -> dict:
    predictions = get_all_predicted_birthdays()
    if not predictions:
        return {
            "total": 0, "by_confidence": {},
            "by_method": {}, "wished": 0,
        }

    by_conf   = {}
    by_method = {}
    wished    = 0

    for p in predictions:
        c = p.get("confidence", "unknown")
        m = p.get("prediction_method", "unknown")
        by_conf[c]   = by_conf.get(c, 0) + 1
        by_method[m] = by_method.get(m, 0) + 1
        if p.get("wish_sent"):
            wished += 1

    return {
        "total"        : len(predictions),
        "by_confidence": by_conf,
        "by_method"    : by_method,
        "wished"       : wished,
    }