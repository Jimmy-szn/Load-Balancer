FROM python:3.10-slim
RUN apt-get update && apt-get install -y sudo curl
RUN curl -fsSL https://get.docker.com | sh
WORKDIR /app
RUN pip install flask requests
COPY . .
CMD ["python", "app.py"]
