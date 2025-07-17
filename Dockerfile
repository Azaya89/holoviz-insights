FROM mambaorg/micromamba:2.3.0

WORKDIR /code

COPY environment.yml /code/environment.yml

RUN micromamba env create -f /code/environment.yml -n appenv \
    && micromamba clean --all --yes

COPY . .

RUN mkdir -p /code/.cache /code/.chroma && chmod 777 /code/.cache /code/.chroma
RUN mkdir -p /home/mambauser/.cache/mamba/proc && chmod -R 777 /home/mambauser/.cache

SHELL ["/bin/bash", "-c"]

ENV MAMBA_DOCKERFILE_ACTIVATE=1
ENV PATH /opt/conda/envs/appenv/bin:$PATH

CMD ["micromamba", "run", "-n", "appenv", "panel", "serve", "/code/app.py", "--address", "0.0.0.0", "--port", "7860", "--allow-websocket-origin", "*"]
