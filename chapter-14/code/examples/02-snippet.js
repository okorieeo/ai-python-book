const socket = new ReconnectingSocket({
  url: async () => {
    const response = await fetch("/api/v1/ws-ticket", { method: "POST", credentials: "include", headers: { "X-CSRFToken": csrf } });
    const { ticket } = await response.json();
    return `wss://api.example.com/ws/chat/?ticket=${ticket}`;
  },
  onStatus: (status) => showConnectionBanner(status),
  onMessage: (message) => {
    if (message.type === "assistant.delta") appendText(message.data.text);
    if (message.type === "assistant.end") finishAnswer(message.data);
    if (message.type === "notification") showToast(message.data.title);
  },
});
socket.connect();
socket.send({ type: "message.send", id: "c-1", data: { conversation_id: id, content: "Hello" } });
