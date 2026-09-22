"""main.py — stage 4 (graph rendering, run manually after the pipeline —
not part of run_pipeline.sh). 2 named chapters, no logic of its own —
pipeline.py says what each chapter consists of, and steps/ says how. See
ARCHITECTURE.md.
"""
from src.services.graph.pipeline import load_and_prepare, render_graphs
from src.services.graph.steps.io import configure_logging


def main():
    configure_logging()

    data = load_and_prepare()
    render_graphs(data)


if __name__ == "__main__":
    main()
