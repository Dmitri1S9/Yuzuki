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


# No persistent server: analyse_service is only ever started via
# `docker compose run analyse_service conda run ... python -m src.services...`,
# which replaces this CMD outright — this is just a harmless default.
CMD ["bash"]

