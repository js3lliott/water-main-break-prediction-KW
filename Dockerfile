# Build image
FROM python:3.10.6-slim-buster

WORKDIR /Users/jordansamek/Desktop/Projects/water-main-break-prediction-KW

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:${PATH}"

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE $PORT

ENTRYPOINT ["streamlit", "run", "st_app.py", "--server.port=$PORT", "--server.address=0.0.0.0"]

HEALTHCHECK CMD curl --fail http://localhost:$PORT/healthz || exit 1