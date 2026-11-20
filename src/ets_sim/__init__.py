"""KTM ETS delay propagation simulator.

Modules:
    config       load config.yaml
    loader       GTFS static feed -> clean ETS station and timetable tables
    topology     shared physical railway graph and fixed sub-blocks
    train        trip and stop data, timetable transforms (buffer, shifted copies)
    events       event log and causal delay attribution
    model        SimPy simulation
    metrics      reliability statistics from simulation output
    experiments  seeded replications and parameter sweeps
"""

__version__ = "0.1.0"
