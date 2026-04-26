# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Python script that monitors **my.devinci.fr** and sends a push notification via **ntfy** when a class attendance check opens.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows

pip install playwright python-dotenv requests workalendar
python -m playwright install chromium

cp .env-example .env  # then fill in credentials
```

## Commands

```bash
# Run the script (must be run from src/)
cd src && python main.py

# Run all tests (from project root)
pytest tests/

# Run a single test
pytest tests/test_changes.py::test_filtrage_examens
```

There is no `requirements.txt` — dependencies are: `playwright`, `python-dotenv`, `requests`, `workalendar`.

## Architecture

Three modules in `src/`:

- **`main.py`** — entry point and main loop. Owns scheduling logic: skips weekends, public holidays, and weeks with no classes (`verifier_semaine_avec_cours`). Calls `traiter_cours()` which places each course into one of two check windows (60s interval within ±15 min of start; 120s interval from +15 min to end of class).

- **`utilisateur.py`** — wraps the Playwright browser session. Handles login via ADFS redirect, daily course refresh (`maj_cours_du_jour`), session expiry detection and reconnection (`_reconnecter`), weekly calendar scan (`verifier_semaine_avec_cours`), and ntfy notification dispatch. Stores the active `planning` list of `Cours` objects.

- **`cours.py`** — represents a single class. `type_appel()` navigates to the attendance URL and returns `"open"`, `"deja_present"`, or `"closed"` based on page content. Handles session expiry mid-check by calling `_reconnecter`.

**Key data flow:** `main.py` initialises one `Utilisateur`, calls `maj_cours_du_jour()` each day to populate `utilisateur.planning`, then loops over that list calling `traiter_cours()` for each `Cours`.

---
 
## Code Conventions
 
- **Language**: French for logs, comments and variable names
- **Logging**: `TimedRotatingFileHandler` — daily rotation, 7 days retention, files stored in `logs/`
- **Private methods**: prefixed with `_` (e.g. `_verifier_session`, `_parser_ligne_cours`)
- **Cognitive complexity**: short, well-structured functions (SonarQube configured, max 15)
- **Timezone**: always use `PARIS_TZ = ZoneInfo("Europe/Paris")`
---

## Important details

- **Working directory**: scripts must run from `src/` — `cours.py` and `utilisateur.py` are imported without package prefixes, so `cd src` before running.
- **`.env` variable names**: `EMAIL_1`, `PASSWORD_1`, `SUJET` (not `SUJET_1` — see `utilisateur.py:189`).
- **Playwright selectors**: `#body_presences` table, `span:has-text('Valider la présence')`, and `.b-weekview-content .b-cal-event-wrap` for the calendar scan. These are fragile — inspect the page if scraping breaks.
- **Exam filtering**: rows where `nom_cours` contains `"examen"` (case-insensitive) are silently skipped in `maj_cours_du_jour`.
- **Tests**: `tests/test_changes.py` uses pytest. `conftest.py` adds `src/` to `sys.path`. Tests 2 and 4 (`test_pas_de_fuite_browser`, `test_scan_calendrier_sans_double_navigation`) require live credentials in `.env` and are auto-skipped when absent. Tests 1, 3, 5 are pure logic with no browser needed. `pytest` must be installed: `pip install pytest`.
