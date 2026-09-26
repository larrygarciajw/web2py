"""
Characterization tests for the web2py modernization effort.

These tests pin the *current* behavior of the framework, including
behavior that is suspected to be defective, so that later refactoring
cannot change it silently. They are intentionally NOT imported by
``gluon/tests/__init__.py`` and therefore do not affect the official
baseline (docs/ai-context/baseline.md).

Conventions
-----------
* Every test class docstring names its plan ID (e.g. ``A1``) and the
  architecture document that describes the behavior.
* Tests whose assertions encode behavior that is probably a defect are
  named ``test_current_*`` and carry a ``PINS-DEFECT: <id>`` tag in their
  docstring. When a later, approved fix changes that behavior, the test is
  expected to fail and must be updated deliberately as part of the fix.
* Tests must not touch the network, bind ports, create symlinks, or
  leave files behind; all global state they change is restored.

Run with (from the repository root)::

    python -m unittest discover -s gluon/tests/characterization -t . -v
"""
