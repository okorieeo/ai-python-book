cd backend
IMAGE=ghcr.io/YOUR_GITHUB_NAME/ai-chat-backend    # lowercase only
TAG=$(git rev-parse --short HEAD)
 
docker build -t $IMAGE:$TAG -t $IMAGE:main .
 
# Log in with a token that has the write:packages permission. The token is read
# from standard input so it never appears in your shell history or process list.
echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_NAME --password-stdin
docker push $IMAGE:$TAG
