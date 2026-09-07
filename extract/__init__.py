"""Extraction layer: pulls raw data from live sources into partitioned parquet.

Nothing in here transforms or cleans. The only jobs are (a) get the bytes
faithfully, (b) preserve geometry, (c) stamp provenance. All cleaning lives in
the dbt staging layer so it is testable and lineage-tracked.
"""
