"""Analysis layer: reads the marts, writes figures. Never writes to the warehouse.

Queries live in `queries.py` so they are importable and testable rather than
buried in notebook cells; `figures.py` renders them.
"""
