FROM python:3.11-slim

# Install R runtime + system deps needed by adobeanalyticsr
RUN apt-get update && apt-get install -y \
    r-base \
    r-base-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install R packages (jsonlite first as a hard dep)
RUN R -e "install.packages(c('jsonlite', 'httr', 'dplyr'), repos='https://cloud.r-project.org')"
RUN R -e "install.packages('adobeanalyticsr', repos='https://cloud.r-project.org')"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Credentials must be injected at runtime — never bake into the image
# Required: AW_CLIENT_ID, AW_CLIENT_SECRET, AW_COMPANY_ID
ENV AW_CLIENT_ID=""
ENV AW_CLIENT_SECRET=""
ENV AW_COMPANY_ID=""

CMD ["python", "server.py"]
