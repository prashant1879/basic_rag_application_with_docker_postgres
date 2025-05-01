FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y libpq-dev build-essential

# Upgrade pip
RUN pip install --upgrade pip

# Create a non-root user
RUN useradd -m appuser

# Set working directory and permissions
WORKDIR /app
COPY . /app
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Install Python dependencies
RUN pip install --user -r requirements.txt

# Export path so Python can find user-installed packages
ENV PATH="/home/appuser/.local/bin:$PATH"

# Expose port and run app
EXPOSE 8000
CMD ["python", "start.py"]
