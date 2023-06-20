# Build image
FROM python:3.10.6-slim-buster

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:${PATH}"

COPY . .

RUN pip install --user --no-cache-dir -r requirements.txt

EXPOSE $PORT

ENTRYPOINT ["streamlit", "run", "st_app.py", "--server.port=$PORT", "--server.address=0.0.0.0"]