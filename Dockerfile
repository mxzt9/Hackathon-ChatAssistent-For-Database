FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV APP_HOST=0.0.0.0 APP_PORT=8000
EXPOSE 8000
CMD ["python", "run.py"]
