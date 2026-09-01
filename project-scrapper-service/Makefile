.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: lint
lint: ## Run linters in format mode
	black ./src ./tests
	mypy ./src
	ruff check ./src ./tests
	pytest ./tests --dead-fixtures --dup-fixtures 

.PHONY: test
test: ## Runs pytest with coverage
	pytest ./tests 

.PHONY: start
start: ## Run program
	poetry run python -m src.main

.PHONY: up
up: ## Up docker-compose
	docker compose up -d

.PHONY: down
down: ## Stop docker-compose
	docker compose down
