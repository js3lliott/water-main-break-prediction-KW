# Build image
FROM python:3.10.6-slim-buster

WORKDIR /app

RUN pip3 install -r requirements.txt

CMD streamlit run st_app.py --server.port=$PORT --server.address=0.0.0.0