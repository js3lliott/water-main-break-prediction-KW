# Build image
FROM python:3.10.6-slim-buster AS build

WORKDIR /app

COPY requirements.txt .

RUN pip install --user --no-cache-dir -r requirements.txt

# Final image
FROM python:3.10.6-slim-buster

WORKDIR /app

COPY --from=build /root/.local /root/.local

COPY st_app.py .

RUN groupadd -r app && useradd --no-log-init -r -g app app \
    && chown -R app:app /app

USER app

EXPOSE 8501

CMD ["streamlit", "run", "st_app.py"]