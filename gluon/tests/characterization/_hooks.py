"""
Mutable record that application code executed by wsgibase can append to,
so tests can observe calls made inside the request (test-only).
"""

CALLS = []


def reset():
    del CALLS[:]
