useEffect(() => {
  const controller = new AbortController();
  const timer = setInterval(refresh, 30_000);
  const subscription = AppState.addEventListener('change', onChange);
  void load({ signal: controller.signal });

  return () => {                 // runs when the screen closes or the dependencies
      change
    controller.abort();
    clearInterval(timer);
    subscription.remove();
  };
}, []);
