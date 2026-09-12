"""
Student Dropout Risk — ML pipeline package.

Console encoding guard
----------------------
Several scripts in this package print box-drawing characters and emoji in
their progress output. On Windows the console defaults to a legacy codepage
(cp1252), and printing those characters raises UnicodeEncodeError, which made
`python src/pipeline.py` fail before it did any work.

Reconfiguring stdout/stderr here — rather than in each entry point — covers
every `python src/<script>.py` invocation, because they all import from `src`.
"""

import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        # Not a reconfigurable text stream (e.g. redirected/closed) - ignore.
        pass
