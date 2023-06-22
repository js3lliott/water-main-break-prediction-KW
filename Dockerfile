# Build image
FROM python:3.10.6-slim-buster

WORKDIR /app

COPY requirements.txt .

COPY st_app.py .

RUN pip install -r requirements.txt

CMD streamlit run st_app.py --server.port=$PORT