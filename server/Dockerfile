FROM python:3.10-slim
WORKDIR /app
RUN pip install flask
COPY server.py .
ENV SERVER_ID=1
CMD ["python", "server.py"]

