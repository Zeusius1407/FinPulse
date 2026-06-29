web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
release: python -c "from backend.database import init_db; init_db()"
