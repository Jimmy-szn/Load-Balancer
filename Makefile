build:
	docker build -t my_server ./server
	docker compose build

up:
	docker rm -f load_balancer 2>/dev/null || true
	docker compose up -d --force-recreate

down:
	docker compose down
	docker ps -q --filter "name=Server" | xargs -r docker stop
	docker ps -aq --filter "name=Server" | xargs -r docker rm
