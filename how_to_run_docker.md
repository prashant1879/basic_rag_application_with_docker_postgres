Absolutely! Here are the **most important Docker and Docker Compose commands** for building, running, and managing your FastAPI + PostgreSQL project.

---

## 🧱 Build the Docker Image

### 🔨 1. Build the FastAPI service (from `docker-compose.yml`)
```bash
docker-compose build
```

> Rebuilds only the service(s) that have changed (like your FastAPI app).

---

## 🚀 Run the Project

### ▶️ 2. Start all services (FastAPI + PostgreSQL)
```bash
docker-compose up
```

> Use `-d` to run in background (detached mode):
```bash
docker-compose up -d
```

---

## 🛑 Stop the Project

### ⏹ 3. Stop containers gracefully
```bash
docker-compose down
```

> This stops and removes containers **but keeps volumes** (i.e., your Postgres data).

### 🧹 4. Stop and **remove all volumes** (database data, etc.)
```bash
docker-compose down -v
```

> Use this if you want a clean start, e.g., to re-run DB init scripts.

---

## 🔁 Rebuild After Dockerfile Changes

### 🔄 5. Rebuild images and restart containers
```bash
docker-compose up --build
```

---

## 🔍 Debug & Logs

### 🧾 6. See logs for all services
```bash
docker-compose logs
```

### 🧾 7. Logs for a specific service
```bash
docker-compose logs fastapi
```

---

## 🐚 Access the Containers

### 🐳 8. Shell into FastAPI container
```bash
docker exec -it <fastapi_container_name> bash
```

### 🐘 9. Shell into PostgreSQL container
```bash
docker exec -it <postgres_container_name> psql -U postgres -d rag-demo
```

> You can find container names with:
```bash
docker ps
```

---

Would you like these commands included in a `README.md` template for your project?