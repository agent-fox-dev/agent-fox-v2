"""Build-time metadata stamped by ``make stamp-version``.

This file is tracked in git with placeholder values.  The Makefile
overwrites ``GIT_REVISION`` before a non-editable install so the
banner can display the correct agent-fox revision rather than the
revision of whatever repository the user happens to be working in.

For editable (dev) installs the banner falls back to reading git
from the package source directory, so this file can stay untouched.
"""

GIT_REVISION: str | None = None
