# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy only necessary files
COPY ServerChanPush2TelegramBot.py /app/
COPY wsgi.py /app/
COPY bot_config_example.json /app/
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Ensure bot_config.json exists
RUN if [ ! -f /app/data/bot_config.json ]; then \
    mkdir -p /app/data && \
    cp /app/bot_config_example.json /app/data/bot_config.json; \
    fi

# Expose the port
EXPOSE 5000

# Run wsgi server with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"]
