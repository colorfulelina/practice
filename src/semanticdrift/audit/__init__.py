"""Semantic-drift auditor (methodology §4.1 / §8.6)."""

from semanticdrift.audit.classify import FAILURE_CATEGORIES, classify_failure
from semanticdrift.audit.run import audit_protocol, audit_text
