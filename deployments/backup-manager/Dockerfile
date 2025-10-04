FROM python:3.11-slim

WORKDIR /app

# Install restic
RUN apt-get update && \
    apt-get install -y wget bzip2 && \
    wget https://github.com/restic/restic/releases/download/v0.17.3/restic_0.17.3_linux_$(dpkg --print-architecture).bz2 && \
    bunzip2 restic_0.17.3_linux_$(dpkg --print-architecture).bz2 && \
    mv restic_0.17.3_linux_$(dpkg --print-architecture) /usr/local/bin/restic && \
    chmod +x /usr/local/bin/restic && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask kubernetes

COPY app.py .

EXPOSE 8080

CMD ["python", "app.py"]
