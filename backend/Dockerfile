#Base image is a slim version of Python 3.11, which is a lightweight image that contains only the essential 
#components needed to run Python applications. This helps reduce the size of the final Docker image and improves build times.
FROM python:3.11-slim

#Sets the working directory inside the container to /app. All subsequent commands will be run from this directory.
WORKDIR /app
ENV PYTHONPATH=/app

#Build Dependencies: Installs the necessary build dependencies for compiling Python packages that require native extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

#Documents which port the containers listen on
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]