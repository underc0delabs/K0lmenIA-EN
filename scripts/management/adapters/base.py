"""Common interface of the test management tool adapters.

Each tool (Xray Cloud, Xray Server/DC, QTM4J, AIO Tests) implements these
operations with its official API. The CLI (management.py) and the agents only use this interface.

Conventions:
- A "case" is the dict returned by readers.read_cases (id, title, description,
  preconditions, priority, tags, type manual|cucumber, steps, gherkin).
- The keys returned are the ones visible in the tool (PROJ-45, PROJ-TC-12...).
- normalized status: passed | failed | blocked | pending | in_progress.
"""


import os


def with_time(text, case):
    """Appends the estimated manual run time to the description (scripts/estimation.py)."""
    e = case.get("estimate")
    if not e:
        return text
    line = f"Estimated manual run time: {e['text']} (k0lmenIA)"
    return f"{text}\n\n{line}".strip() if text else line


def native_time():
    """MANAGEMENT_NATIVE_TIME=0 disables the native time field (Original Estimate, estimatedTime…)."""
    return os.environ.get("MANAGEMENT_NATIVE_TIME", "1").strip() != "0"


def try_with_time(create, with_field, without_field):
    """Creates with the time field; if the tool rejects it (nonexistent field, not on the screen
    or in another format), creates without it. The time is still in the description."""
    from common import ManagementError
    if with_field is without_field:
        return create(without_field)
    try:
        return create(with_field)
    except ManagementError:
        return create(without_field)


def jira_duration(minutes):
    """Jira Original Estimate ("7m", "1h 15m")."""
    import math
    m = int(math.ceil(minutes))
    h, r = divmod(m, 60)
    return " ".join(x for x in (f"{h}h" if h else "", f"{r}m" if r else "") if x) or "1m"


def hhmm(minutes):
    import math
    m = int(math.ceil(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def remote_title(case, length=250):
    """'TC-001 - Title' (or just the title if the case has no ID of its own, e.g. a scenario without @TC-XXX)."""
    title = case["title"] if case["id"] == case["title"] else f'{case["id"]} - {case["title"]}'
    return title[:length]


class Adapter:
    name = "base"
    #: maximum size of an attachment in bytes (None = no known limit)
    attachment_limit = None

    def __init__(self, project, dry_run=False):
        self.project = project
        self.dry_run = dry_run

    # --- Case repository -------------------------------------------------------
    def create_folder(self, path):
        """Creates the folder (and its parents) if it does not exist. Returns its id."""
        raise NotImplementedError

    def create_case(self, case, folder_id, folder_path):
        """Creates the case inside the folder. Returns {"key": ..., "id": ...}."""
        raise NotImplementedError

    def link_case_to_story(self, case, story):
        """Links the case (dict with key/id) to the Jira story (e.g. PROJ-12)."""
        raise NotImplementedError

    # --- Cycles -----------------------------------------------------------------
    def create_cycle(self, name, description="", folder_path=None):
        """Creates the cycle (Test Execution in Xray, Test Cycle in QTM4J/AIO). Returns {"key", "id"}."""
        raise NotImplementedError

    def link_cycle_to_story(self, cycle, story):
        raise NotImplementedError

    def add_cases_to_cycle(self, cycle, cases):
        """cycle and cases: dicts with key/id."""
        raise NotImplementedError

    # --- Results ----------------------------------------------------------------
    def register_result(self, cycle, case, status, comment, evidence):
        """Sets the case status in the cycle, the comment and attaches the evidence
        (list of paths). Returns the list of evidence files that could not be uploaded."""
        raise NotImplementedError
