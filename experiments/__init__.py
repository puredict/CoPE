"""Experiment entry points.

The CoPE repository and upstream OpenVLA both provide modules below the
``experiments`` package. Extend the package path so the local entry points do
not hide OpenVLA's ``experiments.robot`` runtime modules.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
