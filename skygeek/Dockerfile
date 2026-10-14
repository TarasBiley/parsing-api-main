FROM python:3.11.2-slim

WORKDIR /app

RUN apt-get update && apt-get install -y chromium-driver

COPY requirements.txt requirements.txt

RUN  pip install --upgrade pip --no-cache-dir && pip install -r requirements.txt --no-cache-dir

COPY . .

CMD ["/bin/bash", "-c", "cleanup_tmp && exec /bin/bash"]
