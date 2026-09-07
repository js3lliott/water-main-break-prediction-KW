# Local reproducibility only. The app deploys to Streamlit Community Cloud,
# which builds from requirements.txt -- see the note there.
FROM python:3.11-slim

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app/ app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[app]"

EXPOSE 8501

# The app reads the committed parquet bundle under app/data/, so no warehouse
# and no API access are needed at runtime.
CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
