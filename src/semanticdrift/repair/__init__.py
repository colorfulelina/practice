"""Category-restricted repair (methodology §8.7). Cap 5; never patch the code under test."""

from semanticdrift.repair.loop import REPAIR_CAP, repair_protocol
from semanticdrift.repair.weaken import is_property_weakened
