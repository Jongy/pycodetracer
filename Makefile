SRC := tracer.py

LINE_LENGTH := 100

lint: $(SRC)
	python -m isort $(SRC)
	python -m black --line-length=$(LINE_LENGTH) $(SRC)
	chown 1000:1000 $(SRC)  # running in Docker with UID 0 messes ownership :/
	python -m flake8 --max-line-length=$(LINE_LENGTH) $(SRC)
	python -m mypy $(SRC)
