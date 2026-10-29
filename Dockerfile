FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/mpl \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m appuser

COPY common.py step0_setup_and_discover.py step1_extract_reports.py step2_compute_methodology.py step3_generate_html.py run_pipeline.py web_app.py ./

USER appuser
EXPOSE 8080
CMD ["python", "web_app.py"]
