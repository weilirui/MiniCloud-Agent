.PHONY: help up down logs build restart ps clean test test-cov test-integration backend-test golden eval eval-qdrant eval-semantic eval-real eval-agent eval-online frontend-build

# Python interpreter used for local test / eval runs.
# Override it if your dependencies live in a virtualenv, e.g.:
#   make test PY=.venv/Scripts/python
PY ?= python

# Qdrant as seen from the host. Inside compose it is http://qdrant:6333,
# but the host-side mapping is 16333 (6333 lands in the Hyper-V reserved range).
QDRANT_URL ?= http://localhost:16333

help:
	@echo "make up               - 启动全部服务"
	@echo "make down             - 停止并移除容器"
	@echo "make logs             - 查看日志"
	@echo "make build            - 重新构建镜像"
	@echo "make restart          - 重启服务"
	@echo "make ps               - 查看运行状态"
	@echo "make test             - 本地单元测试 + e2e（无需外部服务）"
	@echo "make test-cov         - 同上，附带覆盖率报告"
	@echo "make test-integration - 连接真实 PostgreSQL / Qdrant 的测试"
	@echo "make backend-test     - 在 Docker 容器内跑测试"
	@echo "make golden           - 重新生成评测黄金集"
	@echo "make eval             - 离线检索评测（哈希向量，只能相对比较）"
	@echo "make eval-qdrant      - 用真实 Qdrant 跑评测（仍是哈希向量）"
	@echo "make eval-semantic    - 本地语义模型 bge-small-zh（免费，可作绝对数值）"
	@echo "make eval-real        - 托管 embedding API（产生费用）"
	@echo "make eval-agent       - Agent 工具选择评测（真实 LLM，产生费用）"
	@echo "make eval-online      - Agent 轨迹 + 生成质量（真实 LLM，产生费用）"
	@echo "make clean            - 清理所有数据卷（危险！）"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

restart:
	docker compose restart

ps:
	docker compose ps

# ---------- tests ----------

test:
	cd backend && $(PY) -m pytest -q

test-cov:
	cd backend && $(PY) -m pytest -q --cov=app --cov-report=term-missing

test-integration:
	cd backend && $(PY) -m pytest -q --run-integration

# original target: run the suite inside the running container
backend-test:
	# The runtime image deliberately ships without test deps (it is the image that
	# gets deployed); tests/eval/scripts are bind-mounted by docker-compose instead.
	# The install is idempotent, so only the first run pays for it.
	docker compose exec backend pip install -q pytest "pytest-asyncio>=0.24,<1.0" pytest-cov
	docker compose exec backend python -m pytest -v

# ---------- evaluation ----------

golden:
	cd backend && $(PY) scripts/build_golden_dataset.py

eval:
	cd backend && $(PY) -m eval.runner

eval-qdrant:
	cd backend && $(PY) -m eval.runner --backend qdrant --qdrant-url $(QDRANT_URL)

eval-semantic:
	cd backend && $(PY) -m eval.runner --embedder local

eval-real:
	cd backend && $(PY) -m eval.runner --backend qdrant --qdrant-url $(QDRANT_URL) --embedder openai

eval-agent:
	cd backend && $(PY) -m eval.online_runner --suite agent

eval-online:
	cd backend && $(PY) -m eval.online_runner --suite all

clean:
	@echo "⚠️  这将删除所有数据卷（包括 PG/Qdrant 数据）"
	@read -p "确认输入 yes: " ans && [ $$ans = "yes" ] && docker compose down -v && rm -rf data/
