docker ps                       # running containers
docker ps -a                    # all containers
docker images                   # downloaded/built images
docker logs -f <container>      # follow logs
docker exec -it <container> bash   # open a shell inside a container
docker compose up -d            # start all services in the background
docker compose down             # stop and remove them
docker compose logs -f          # follow logs of all services
docker system prune             # clean up unused data (read the prompt first)
