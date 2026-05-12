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

CMD ["conda","run","--no-capture-output","-n","analyse_service","uvicorn","app.main:app","--host","0.0.0.0","--port","8044", "--no-access-log"]

