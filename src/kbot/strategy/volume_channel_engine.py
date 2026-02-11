"""Compatibility shim: provide VolumeChannelEngine exported name for imports.

The old Volume Channel Flow implementation was removed per project decision.
This module re-exports the new PeakTroughEngine under the old name so code and
importers continue to work while transitioning.
"""
from .peak_trough_engine import PeakTroughEngine as VolumeChannelEngine
