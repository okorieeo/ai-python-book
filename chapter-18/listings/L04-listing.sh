npm run build
npm start -- -p 3100 &

curl -s localhost:3100/chat/welcome | grep -o "What can you help me with?"
curl -s localhost:3100/pricing | grep -o "<title>[^<]*</title>"
for p in / /pricing /chat /chat/welcome /chat/does-not-exist; do
  echo "$p -> $(curl -s -o /dev/null -w '%{http_code}' localhost:3100$p)"
done
 example output
What can you help me with?
<title>Pricing · Chat App</title>
/ -> 200
/pricing -> 200
/chat -> 200
/chat/welcome -> 200
/chat/does-not-exist -> 200
