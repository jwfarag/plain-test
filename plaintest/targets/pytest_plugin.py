"""A pytest plugin that PytestTarget.run loads into the test process with `-p`.

It does two things:
- registers the `check` marker, so `@pytest.mark.check("id")` raises no warning;
- records each test's outcome to the JSON file named by $PLAINTEST_RESULTS.

It exists because pytest's own reports can't reliably tell an assertion that didn't hold
(the test disagrees with the code) from a test that crashed (the test is broken).
Here we can look at the exception itself.
"""

import json
import os

import pytest

RESULTS_ENV = "PLAINTEST_RESULTS"
_results: dict[str, dict[str, str]] = {}


def pytest_configure(config):
    config.addinivalue_line("markers", "check(id): the plaintest Check this test covers")


def pytest_collectreport(report):
    if report.failed:  # an import error, a syntax error: every test in the file is broken
        _results[report.nodeid] = {"outcome": "error", "detail": _short(report.longreprtext)}


def pytest_runtest_makereport(item, call):
    if call.excinfo is None:
        if call.when == "call":
            _results.setdefault(item.nodeid, {"outcome": "passed", "detail": ""})
        return
    asserted = call.when == "call" and call.excinfo.errisinstance((AssertionError, pytest.fail.Exception))
    _results[item.nodeid] = {
        "outcome": "failed" if asserted else "error",
        "detail": _short(str(call.excinfo.getrepr(style="short"))),
    }


def pytest_sessionfinish(session):
    path = os.environ.get(RESULTS_ENV)
    if path:
        with open(path, "w") as f:
            json.dump(_results, f, indent=2)


def _short(text: str, limit: int = 1500) -> str:
    return text if len(text) <= limit else "…" + text[-limit:]
