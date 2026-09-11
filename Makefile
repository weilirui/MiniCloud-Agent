.PHONY: help up down logs build restart ps clean test backend-test frontend-build

help:
	@echo "make up          - 启动全部服务"
	@echo "make down        - 停止并移除容器"
	@echo "make logs        - 查看日志"
	@echo "make build       - 重新构建镜像"
	@echo "make restart     - 重启服务"
	@echo "make ps          - 查看运行状态"
	@echo "make test        - 后端测试"
	@echo "make clean       - 清理所有数据卷（危险！）"

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

backend-test:
	docker compose exec backend pytest -v

clean:
	@echo "⚠️  这将删除所有数据卷（包括 PG/Qdrant 数据）"
	@read -p "确认输入 yes: " ans && [ $$ans = "yes" ] && docker compose down -v && rm -rf data/