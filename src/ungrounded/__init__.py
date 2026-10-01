"""Measure how often your LLM agent reaches for the wrong tool when it
cannot ground an entity in a request.

    from ungrounded import Probe
    result = Probe(model="claude-sonnet-4-6", tools=MY_TOOLS).run()
    print(result.summary())

Method and data: https://doi.org/10.5281/zenodo.21958705
"""

from .core import CONDITIONS, Decoy, Trial, Triple
from .probe import Probe, Result
from .report import Scorecard
from .stimuli import DEFAULT_TRIPLES

__version__ = "0.3.0"
__all__ = ["Probe", "Result", "Scorecard", "Triple", "Decoy", "Trial",
           "CONDITIONS", "DEFAULT_TRIPLES"]
