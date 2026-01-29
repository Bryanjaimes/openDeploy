FROM python:3.11-slim

WORKDIR /app

COPY operator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY operator/main.py ./main.py

CMD ["python", "/app/main.py"]