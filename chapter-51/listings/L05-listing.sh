docker rm -f frontend backend redis db
docker network rm appnet
# Keep the data volume, or delete it deliberately:
# docker volume rm chat-pgdata
 
cd ..
git add backend frontend tools .gitattributes .gitignore
git status --short
git commit -m "Add Docker images for backend and frontend, with policy checks"
