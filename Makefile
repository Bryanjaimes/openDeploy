.PHONY: help test lint build run deploy clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

# --- Python ---

test: ## Run Python unit tests
	python -m pytest backend/tests/ -v --tb=short

lint: ## Lint Python code
	python -m ruff check backend/ models/ scripts/

fmt: ## Format Python code
	python -m ruff format backend/ models/ scripts/

# --- Go CLI ---

build: ## Build the Go CLI binary
	cd cli && go build -o ../bin/opendeploy ./cmd/opendeploy

build-cli-linux: ## Cross-compile CLI for Linux
	cd cli && GOOS=linux GOARCH=amd64 go build -o ../bin/opendeploy-linux ./cmd/opendeploy

go-test: ## Run Go unit tests
	cd cli && go test ./...

# --- Docker ---

run: ## Start local stack (API + WebRTC + Prometheus + Grafana)
	docker compose up -d --build

run-vllm: ## Start vLLM runner
	docker compose -f docker-compose.vllm.yml up -d

stop: ## Stop all containers
	docker compose down

# --- Infrastructure ---

deploy-aws: ## Deploy to AWS via Terraform
	cd infra/aws && terraform init && terraform apply

# --- Operator ---

operator-build: ## Build operator Docker image
	docker build -t opendeploy-operator:dev -f operator/Dockerfile operator/

# --- Cleanup ---

clean: ## Remove build artifacts and caches
	rm -rf bin/ artifacts/ __pycache__ backend/__pycache__ models/__pycache__
	find . -name '*.pyc' -delete
