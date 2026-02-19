FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN GECKO_VERSION=$(wget -qO- https://api.github.com/repos/mozilla/geckodriver/releases/latest \
    | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/') \
    && wget -q "https://github.com/mozilla/geckodriver/releases/download/v${GECKO_VERSION}/geckodriver-v${GECKO_VERSION}-linux64.tar.gz" \
    -O /tmp/geckodriver.tar.gz \
    && tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin/ \
    && rm /tmp/geckodriver.tar.gz \
    && chmod +x /usr/local/bin/geckodriver

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite+aiosqlite:///./data/bot.db

CMD ["python", "main.py"]
