.PHONY: install uninstall test doctor lint clean

install:
	sudo ./install.sh

uninstall:
	sudo ./uninstall.sh

test:
	python3 -m pytest tests/ -v

doctor:
	sudo ./bin/doctor

lint:
	python3 -m py_compile lib/*.py bin/ssh-free bin/ssh-free-stop bin/doctor bin/status bin/tui

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache

.DEFAULT_GOAL := lint
