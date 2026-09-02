FROM python:3.13-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

USER 65532:65532
ENTRYPOINT ["storygraph-audiobookshelf-sync"]
