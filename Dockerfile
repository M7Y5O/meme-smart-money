FROM python:3.12-slim
WORKDIR /app
COPY msm ./msm
ENV PYTHONUNBUFFERED=1
# DB_PATH should point at a mounted volume (e.g. /data/msm.sqlite3) so state survives redeploys
CMD ["python", "-m", "msm", "run"]
