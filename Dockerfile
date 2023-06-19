# Build image
FROM python:3.10.6-slim-buster

WORKDIR /app

ADD . /app

RUN pip install --user --no-cache-dir -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "st_app.py"]