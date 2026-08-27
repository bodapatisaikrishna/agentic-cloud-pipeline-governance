"""Entry point for ``python -m acde.migrations`` (a package needs this; ``__init__.py``'s own
``if __name__ == "__main__"`` guard is never reached via ``-m``).
"""

from acde.migrations import main

if __name__ == "__main__":
    main()
