FROM condaforge/mambaforge:latest

ENV MAMBA_NO_BANNER=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY analyse.yml /app/analyse.yml
RUN mamba env create -n analyse_service -f /app/analyse.yml && mamba clean -afy

SHELL ["bash", "-lc"]

COPY . /app

EXPOSE 8044

# Default CMD: the API DCS calls to confirm reviewed data (src/api/main.py).
# `docker compose up -d analyse_service` runs this persistently; pipeline
# stages still run as one-off `docker compose run analyse_service conda run
# ... python -m src.services...` invocations, which replace this CMD outright
# and exit when the stage finishes — both use the same image.
CMD ["conda", "run", "--no-capture-output", "-n", "analyse_service", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8044"]

